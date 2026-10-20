"""Small steps the deploy / backup workflows run (stdlib only; secrets come from the environment).

    python deploy/ci.py registry               # print the registry name, write a push login to ~/.docker
    python deploy/ci.py wait-live <version> [preview]   # wait until https://<domain> (or the staging site)
                                                        # serves <version> (through Access)
    python deploy/ci.py registry-gc            # drop old image tags (after each deploy)
    python deploy/ci.py registry-collect       # garbage-collect the registry (daily; pushes wait for it)
    python deploy/ci.py r2-env                 # S3 credentials for the backup bucket, as GITHUB_ENV lines
    python deploy/ci.py snapshot               # weekly snapshot of the data volume, keep the newest 4

Nothing secret or identifying is printed (the repo and its logs are public).
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from provision import (BUCKET, DOMAIN, PREVIEW_DOMAIN, REPO_IMAGE, VOLUME, Cloudflare, DigitalOcean, Http,  # noqa: E402
                       VERSION_PATH, ProvisionError, log, mask, need)

KEEP_TAGS = 3          # the newest builds by commit (the newest is main)
ALWAYS_KEEP = {"main", "preview"}     # the real site's and the staging site's current images
KEEP_SNAPSHOTS = 4
GC_WAIT = 45 * 60      # a garbage collection makes the registry read-only; pushes wait this long for it


def cf() -> Cloudflare:
    return Cloudflare(Http("https://api.cloudflare.com/client/v4", need("CLOUDFLARE_API_TOKEN")))


def do() -> DigitalOcean:
    return DigitalOcean(Http("https://api.digitalocean.com", need("DIGITALOCEAN_TOKEN")))


def github_out(name: str, value: str, file: str = "GITHUB_OUTPUT") -> None:
    path = os.environ.get(file)
    if path:
        with open(path, "a") as f:
            f.write(f"{name}={value}\n")


def registry() -> str:
    d = do()
    name = d.registry(apply=False)
    if not name:
        raise ProvisionError("no container registry yet: run the Provision workflow first")
    wait_gc(d, name)
    creds = d.http("GET", "/v2/registry/docker-credentials?read_write=true&expiry_seconds=3600")
    for reg in creds.get("auths", {}).values():
        mask(reg.get("auth", ""))
    cfg = Path.home() / ".docker" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(creds))
    cfg.chmod(0o600)
    github_out("name", name)
    log(f"registry {name}")
    return name


def _get(url: str, headers: dict) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=headers | {"User-Agent": "lacuna-deploy"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, {}
    except (OSError, ValueError):
        return 0, {}


def wait_live(version: str, timeout: float = 30 * 60, poll: float = 20, domain: str = DOMAIN) -> None:
    """Poll <domain>/api/version (open through a path-scoped Access bypass, deploy/provision.py) until the
    server runs `version`. No Cloudflare API call: its service-token API answered 504 for hours (2026-10-20)."""
    end, seen = time.time() + timeout, None
    while time.time() < end:
        status, body = _get(f"https://{domain}{VERSION_PATH}", {})
        live = body.get("version")
        if live == version:
            log(f"live: {version}")
            break
        if (status, live) != seen:
            log(f"waiting: site answers {status}, version {live or '-'}")
            seen = (status, live)
        time.sleep(poll)
    else:
        raise ProvisionError(f"{version} not live after {int(timeout / 60)} min: a long job (import/export) may "
                             "still be running on the server, or the new version failed to start and the server "
                             "went back to the previous one")
    try:
        _sweep_check_tokens(cf())
    except ProvisionError as e:
        log(f"could not delete old check tokens (tried again next deploy): {e}")


def _sweep_check_tokens(c) -> None:
    """Delete the service tokens the old check made per run (lacuna-deploy-check-*): runs cancelled or
    answered 504 left some behind, and the account caps how many it keeps."""
    for t in c.r("GET", f"/accounts/{c.account}/access/service_tokens") or []:
        if t.get("name", "").startswith("lacuna-deploy-check-"):
            c.r("DELETE", f"/accounts/{c.account}/access/service_tokens/{t['id']}")


def wait_gc(d: DigitalOcean, name: str, timeout: float = GC_WAIT, poll: float = 30) -> None:
    """While a garbage collection runs the registry is read-only and refuses pushes with 401; wait it out."""
    until = time.time() + timeout
    while True:
        status, body = d.http.send("GET", f"/v2/registry/{name}/garbage-collection")
        state = (body.get("garbage_collection") or {}).get("status", "") if status == 200 else ""
        if not state or state in ("succeeded", "failed", "cancelled"):
            return
        if time.time() > until:
            raise ProvisionError(f"registry garbage collection still running ({state}); try again later")
        log(f"registry garbage collection running ({state}); waiting before pushing")
        time.sleep(poll)


def registry_collect() -> None:
    """Free the space of deleted tags. Not after every deploy: the registry is read-only meanwhile, and a
    deploy that starts during it waits (wait_gc)."""
    d = do()
    name = d.registry(apply=False)
    wait_gc(d, name)
    status, _ = d.http.send("POST", f"/v2/registry/{name}/garbage-collection", {"type": "untagged manifests and unreferenced blobs"})
    log(f"garbage collection {'started' if status in (200, 201) else 'skipped'}")


def registry_gc() -> None:
    d = do()
    name = d.registry(apply=False)
    tags = d.http("GET", f"/v2/registry/{name}/repositories/{REPO_IMAGE}/tags?per_page=100").get("tags", [])
    tags.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
    builds = [t["tag"] for t in tags if t["tag"] not in ALWAYS_KEEP]
    keep = ALWAYS_KEEP | set(builds[:KEEP_TAGS])
    old = [t["tag"] for t in tags if t["tag"] not in keep]
    for tag in old:
        d.http("DELETE", f"/v2/registry/{name}/repositories/{REPO_IMAGE}/tags/{tag}")
    if old:
        log(f"removed {len(old)} old image tag(s); the daily collection frees their space")


def r2_env() -> None:
    """The deploy token itself can read R2: key id = token id, secret = sha256(token)."""
    token = need("CLOUDFLARE_API_TOKEN")
    c = cf()
    tid = c.r("GET", "/user/tokens/verify")["id"]
    secret = hashlib.sha256(token.encode()).hexdigest()
    mask(secret)
    for k, v in {"AWS_ACCESS_KEY_ID": tid, "AWS_SECRET_ACCESS_KEY": secret, "AWS_DEFAULT_REGION": "auto",
                 "RESTIC_REPOSITORY": f"s3:https://{c.account}.r2.cloudflarestorage.com/{BUCKET}"}.items():
        github_out(k, v, "GITHUB_ENV")


def snapshot() -> None:
    d = do()
    vols = d.http("GET", f"/v2/volumes?name={VOLUME}").get("volumes", [])
    if not vols:
        raise ProvisionError("no data volume yet")
    vid = vols[0]["id"]
    d.http("POST", f"/v2/volumes/{vid}/snapshots", {"name": f"{VOLUME}-{time.strftime('%Y%m%d')}", "tags": ["lacuna"]})
    snaps = d.http("GET", f"/v2/volumes/{vid}/snapshots?per_page=100").get("snapshots", [])
    snaps.sort(key=lambda s: s.get("created_at", ""), reverse=True)
    for s in snaps[KEEP_SNAPSHOTS:]:
        d.http("DELETE", f"/v2/snapshots/{s['id']}")
    log(f"snapshot taken; keeping {min(len(snaps), KEEP_SNAPSHOTS)}")


def main(argv: list[str]) -> int:
    cmds = {"registry": registry, "registry-gc": registry_gc, "registry-collect": registry_collect, "r2-env": r2_env, "snapshot": snapshot}
    try:
        if argv[:1] == ["wait-live"] and len(argv) == 2:
            wait_live(argv[1])
        elif argv[:1] == ["wait-live"] and len(argv) == 3 and argv[2] == "preview":
            wait_live(argv[1], domain=PREVIEW_DOMAIN)
        elif len(argv) == 1 and argv[0] in cmds:
            cmds[argv[0]]()
        else:
            print(__doc__)
            return 2
    except ProvisionError as e:
        print(f"::error::{e}" if os.environ.get("GITHUB_ACTIONS") == "true" else f"error: {e}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
