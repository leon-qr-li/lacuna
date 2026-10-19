"""Small steps the deploy / backup workflows run (stdlib only; secrets come from the environment).

    python deploy/ci.py registry               # print the registry name, write a push login to ~/.docker
    python deploy/ci.py wait-live <version>    # wait until https://<domain> serves <version> (through Access)
    python deploy/ci.py registry-gc            # drop old image tags + garbage-collect (free registry tier)
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
from provision import (BUCKET, DOMAIN, REPO_IMAGE, VOLUME, Cloudflare, DigitalOcean, Http,  # noqa: E402
                       ProvisionError, log, mask, need)

KEEP_TAGS = 3          # main + two previous builds by commit
KEEP_SNAPSHOTS = 4


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


def wait_live(version: str, timeout: float = 30 * 60, poll: float = 20) -> None:
    """A short-lived Access service token (deleted afterwards) lets this job through the front door."""
    c = cf()
    a = c.account
    tok = c.r("POST", f"/accounts/{a}/access/service_tokens",
              {"name": f"lacuna-deploy-check-{os.environ.get('GITHUB_RUN_ID', 'local')}", "duration": "8760h"})
    mask(tok["client_secret"])
    headers = {"CF-Access-Client-Id": tok["client_id"], "CF-Access-Client-Secret": tok["client_secret"]}
    try:
        end, seen = time.time() + timeout, None
        while time.time() < end:
            status, body = _get(f"https://{DOMAIN}/api/health", headers)
            live = body.get("version")
            if live == version:
                log(f"live: {version}")
                return
            if (status, live) != seen:
                log(f"waiting: site answers {status}, version {live or '-'}")
                seen = (status, live)
            time.sleep(poll)
        raise ProvisionError(f"{version} not live after {int(timeout / 60)} min: a long job (import/export) may "
                             "still be running on the server, or the new version failed to start and the server "
                             "went back to the previous one")
    finally:
        c.r("DELETE", f"/accounts/{a}/access/service_tokens/{tok['id']}")
        for t in c.r("GET", f"/accounts/{a}/access/service_tokens") or []:     # leftovers from cancelled runs
            if t.get("name", "").startswith("lacuna-deploy-check-"):
                c.r("DELETE", f"/accounts/{a}/access/service_tokens/{t['id']}")


def registry_gc() -> None:
    d = do()
    name = d.registry(apply=False)
    tags = d.http("GET", f"/v2/registry/{name}/repositories/{REPO_IMAGE}/tags?per_page=100").get("tags", [])
    tags.sort(key=lambda t: t.get("updated_at", ""), reverse=True)
    keep = {"main"} | {t["tag"] for t in tags[:KEEP_TAGS]}
    old = [t["tag"] for t in tags if t["tag"] not in keep]
    for tag in old:
        d.http("DELETE", f"/v2/registry/{name}/repositories/{REPO_IMAGE}/tags/{tag}")
    if old:
        status, _ = d.http.send("POST", f"/v2/registry/{name}/garbage-collection", {"type": "untagged manifests and unreferenced blobs"})
        log(f"removed {len(old)} old image(s); garbage collection {'started' if status in (200, 201) else 'skipped'}")


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
    cmds = {"registry": registry, "registry-gc": registry_gc, "r2-env": r2_env, "snapshot": snapshot}
    try:
        if argv[:1] == ["wait-live"] and len(argv) == 2:
            wait_live(argv[1])
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
