"""Create or update LACUNA's cloud setup (decision cloud-deploy). Idempotent: run it again any time.

    python deploy/provision.py plan        # show what exists / would be created, change nothing
    python deploy/provision.py apply       # create what is missing; never deletes data
    python deploy/provision.py recreate    # also replace the server (data volume kept): new host config, rotated keys

Run by .github/workflows/provision.yml with the repo's secrets in the environment:
DIGITALOCEAN_TOKEN, CLOUDFLARE_API_TOKEN, ACCESS_EMAILS, BACKUP_PASSWORD, ANTHROPIC_API_KEY, RESEND_API_KEY.

What it sets up
- DigitalOcean (SFO3): container registry, a 50 GB data volume (`/data`, the whole workspace), a firewall
  with NO inbound rules, one 4 vCPU / 8 GB droplet whose first boot (cloud-init, deploy/host/) mounts the
  volume, installs Docker, restic and the updater, and starts cloudflared.
- Cloudflare: a remotely managed tunnel to the app, the DNS record, an Access application with an email
  allow-list group (one-time email codes), an R2 bucket for backups, and two narrow API tokens for the
  server (backup bucket only; Access groups only, for in-app invites).

The repo is public and so are workflow logs: nothing secret or identifying (IP, emails, tokens) is printed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DOMAIN = os.environ.get("LACUNA_DOMAIN", "lacunastudio.app")
REGION = os.environ.get("LACUNA_REGION", "sfo3")
SIZE = os.environ.get("LACUNA_SIZE", "s-4vcpu-8gb")
# same price class (4 vCPU / 8 GB): DigitalOcean sometimes stops offering one of these in a region
SIZE_FALLBACKS = ("s-4vcpu-8gb", "s-4vcpu-8gb-amd", "s-4vcpu-8gb-intel")
VOLUME_GB = int(os.environ.get("LACUNA_VOLUME_GB", "50"))
NAME = "lacuna"
TAG = "lacuna"
VOLUME = "lacuna-data"
FIREWALL = "lacuna-no-inbound"
REGISTRY = os.environ.get("LACUNA_REGISTRY", "lacunastudio")
REPO_IMAGE = "lacuna"
BUCKET = "lacuna-backup"
ACCESS_GROUP = "LACUNA invited"
ACCESS_APP = "LACUNA"
ACCESS_POLICY = "LACUNA invited people"
DEPLOY_POLICY = "LACUNA deploy checks"
APP_PORT = 8765
TOKEN_BACKUP = "lacuna-server-backup"
TOKEN_INVITES = "lacuna-server-invites"
PERM_R2_BUCKET = "Workers R2 Storage Bucket Item Write"
PERM_ACCESS_GROUPS = "Access: Organizations, Identity Providers, and Groups Write"


class ProvisionError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(msg, flush=True)


def mask(value: str) -> None:
    """Hide a value in GitHub Actions logs from here on."""
    if value and os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{value}", flush=True)


class Http:
    """JSON over HTTPS with a bearer token. Tests replace `send`."""

    def __init__(self, base: str, token: str):
        self.base, self.token = base, token

    def send(self, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json", "User-Agent": "lacuna-provision"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw) if raw else {}
            except ValueError:
                return e.code, {"raw": raw[:300].decode("utf-8", "replace")}

    def __call__(self, method: str, path: str, body: dict | None = None, ok=(200, 201, 202, 204)) -> dict:
        status, out = self.send(method, path, body)
        if status not in ok:
            # error bodies name what failed; they carry no secrets
            raise ProvisionError(f"{method} {path.split('?')[0]} -> {status}: {json.dumps(out)[:400]}")
        return out


# ------------------------------------------------------------------------------------------ Cloudflare
class Cloudflare:
    def __init__(self, http: Http, domain: str = DOMAIN):
        self.http, self.domain = http, domain
        self._account = self._zone = None

    def r(self, method: str, path: str, body: dict | None = None):
        out = self.http(method, path, body)
        if isinstance(out, dict) and out.get("success") is False:
            raise ProvisionError(f"Cloudflare {method} {path.split('?')[0]}: {out.get('errors')}")
        return out.get("result") if isinstance(out, dict) and "result" in out else out

    @property
    def account(self) -> str:
        if self._account is None:
            zones = self.r("GET", f"/zones?name={urllib.parse.quote(self.domain)}")
            if not zones:
                raise ProvisionError(f"the Cloudflare token cannot see the zone {self.domain}")
            self._zone, self._account = zones[0]["id"], zones[0]["account"]["id"]
        return self._account

    @property
    def zone(self) -> str:
        _ = self.account
        return self._zone

    def team_domain(self) -> str:
        try:
            org = self.r("GET", f"/accounts/{self.account}/access/organizations")
        except ProvisionError as e:
            raise ProvisionError("Cloudflare Zero Trust is not set up yet (one.dash.cloudflare.com → team name, Free plan)") from e
        if not org or not org.get("auth_domain"):
            raise ProvisionError("Cloudflare Zero Trust is not set up yet (one.dash.cloudflare.com → team name, Free plan)")
        return org["auth_domain"]

    # ---- tunnel + DNS
    def tunnel(self, apply: bool) -> tuple[str | None, str | None]:
        a = self.account
        found = self.r("GET", f"/accounts/{a}/cfd_tunnel?name={NAME}&is_deleted=false") or []
        if found:
            tid = found[0]["id"]
        elif apply:
            tid = self.r("POST", f"/accounts/{a}/cfd_tunnel", {"name": NAME, "config_src": "cloudflare"})["id"]
            log("created tunnel")
        else:
            log("would create tunnel")
            return None, None
        if apply:
            self.r("PUT", f"/accounts/{a}/cfd_tunnel/{tid}/configurations", {"config": {"ingress": [
                {"hostname": self.domain, "service": f"http://lacuna:{APP_PORT}", "originRequest": {}},
                {"service": "http_status:404"}]}})
        token = self.r("GET", f"/accounts/{a}/cfd_tunnel/{tid}/token") if apply else None
        if token:
            mask(token)
        return tid, token

    def dns(self, tunnel_id: str | None, apply: bool) -> None:
        target = f"{tunnel_id}.cfargotunnel.com" if tunnel_id else None
        recs = self.r("GET", f"/zones/{self.zone}/dns_records?name={urllib.parse.quote(self.domain)}") or []
        rec = {"type": "CNAME", "name": self.domain, "content": target, "proxied": True, "ttl": 1,
               "comment": "LACUNA tunnel (deploy/provision.py)"}
        cname = [x for x in recs if x["type"] == "CNAME"]
        others = [x for x in recs if x["type"] in ("A", "AAAA")]
        if others:
            raise ProvisionError(f"{self.domain} already has A/AAAA records; remove them in the Cloudflare DNS page first")
        if not apply or not target:
            log("DNS record: " + ("ok" if cname and cname[0]["content"] == target else "would be set"))
            return
        if not cname:
            self.r("POST", f"/zones/{self.zone}/dns_records", rec)
            log("created DNS record")
        elif cname[0]["content"] != target or not cname[0]["proxied"]:
            self.r("PUT", f"/zones/{self.zone}/dns_records/{cname[0]['id']}", rec)
            log("updated DNS record")

    # ---- Access
    def one_time_pin(self, apply: bool) -> str | None:
        a = self.account
        idps = self.r("GET", f"/accounts/{a}/access/identity_providers") or []
        otp = next((i for i in idps if i.get("type") == "onetimepin"), None)
        if otp:
            return otp["id"]
        if not apply:
            log("would add the email one-time-code login")
            return None
        return self.r("POST", f"/accounts/{a}/access/identity_providers",
                      {"name": "Email code", "type": "onetimepin", "config": {}})["id"]

    def group(self, emails: list[str], apply: bool) -> str | None:
        """The invite list. Emails from ACCESS_EMAILS are added; people invited in the app are kept."""
        a = self.account
        groups = self.r("GET", f"/accounts/{a}/access/groups") or []
        g = next((x for x in groups if x.get("name") == ACCESS_GROUP), None)
        want = [{"email": {"email": e}} for e in emails]
        if g is None:
            if not apply:
                log(f"would create the invite list with {len(emails)} email(s)")
                return None
            log(f"created the invite list ({len(emails)} email(s))")
            return self.r("POST", f"/accounts/{a}/access/groups", {"name": ACCESS_GROUP, "include": want})["id"]
        have = {(r.get("email") or {}).get("email", "").lower() for r in g.get("include", [])}
        missing = [w for w in want if w["email"]["email"] not in have]
        if missing and apply:
            self.r("PUT", f"/accounts/{a}/access/groups/{g['id']}",
                   {"name": ACCESS_GROUP, "include": g.get("include", []) + missing,
                    "exclude": g.get("exclude", []), "require": g.get("require", [])})
            log(f"added {len(missing)} email(s) to the invite list")
        return g["id"]

    def policy(self, name: str, body: dict, apply: bool) -> str | None:
        a = self.account
        pols = self.r("GET", f"/accounts/{a}/access/policies") or []
        p = next((x for x in pols if x.get("name") == name), None)
        if not apply:
            return p["id"] if p else None
        if p:
            self.r("PUT", f"/accounts/{a}/access/policies/{p['id']}", {"name": name, **body})
            return p["id"]
        return self.r("POST", f"/accounts/{a}/access/policies", {"name": name, **body})["id"]

    def application(self, group_id: str | None, idp_id: str | None, apply: bool) -> str | None:
        """The Access application in front of the site; returns its audience tag (CF_ACCESS_AUD)."""
        a = self.account
        people = self.policy(ACCESS_POLICY, {"decision": "allow", "include": [{"group": {"id": group_id}}],
                                             "session_duration": "24h"}, apply and bool(group_id))
        checks = self.policy(DEPLOY_POLICY, {"decision": "non_identity",
                                             "include": [{"any_valid_service_token": {}}]}, apply)
        apps = self.r("GET", f"/accounts/{a}/access/apps") or []
        app = next((x for x in apps if x.get("domain") == self.domain), None)
        body = {"name": ACCESS_APP, "type": "self_hosted", "domain": self.domain, "session_duration": "24h",
                "app_launcher_visible": False, "auto_redirect_to_identity": True,
                "allowed_idps": [idp_id] if idp_id else [], "http_only_cookie_attribute": True,
                "same_site_cookie_attribute": "lax",
                "policies": [{"id": people, "precedence": 1}, {"id": checks, "precedence": 2}]}
        if not apply:
            log("Access application: " + ("ok" if app else "would be created"))
            return app.get("aud") if app else None
        if app:
            app = self.r("PUT", f"/accounts/{a}/access/apps/{app['id']}", body)
        else:
            app = self.r("POST", f"/accounts/{a}/access/apps", body)
            log("created the Access application")
        return app["aud"]

    # ---- R2 + scoped tokens for the server
    def bucket(self, apply: bool) -> None:
        a = self.account
        try:
            names = [b["name"] for b in (self.r("GET", f"/accounts/{a}/r2/buckets") or {}).get("buckets", [])]
        except ProvisionError as e:
            raise ProvisionError("R2 is not enabled on the Cloudflare account yet (dashboard → R2)") from e
        if BUCKET in names:
            return
        if apply:
            self.r("POST", f"/accounts/{a}/r2/buckets", {"name": BUCKET, "locationHint": "wnam"})
            log("created the backup bucket")
        else:
            log("would create the backup bucket")

    def _perm(self, name: str) -> str:
        groups = self.r("GET", "/user/tokens/permission_groups") or []
        g = next((x for x in groups if x.get("name") == name), None)
        if not g:
            raise ProvisionError(f"Cloudflare permission group not found: {name}")
        return g["id"]

    def server_token(self, name: str, perm: str, resources: dict) -> tuple[str, str]:
        """A fresh token (older ones of the same name are deleted): (id, value)."""
        for t in self.r("GET", "/user/tokens?per_page=100") or []:
            if t.get("name") == name:
                self.r("DELETE", f"/user/tokens/{t['id']}")
        out = self.r("POST", "/user/tokens", {"name": name, "policies": [
            {"effect": "allow", "resources": resources, "permission_groups": [{"id": self._perm(perm)}]}]})
        mask(out["value"])
        return out["id"], out["value"]

    def backup_credentials(self) -> dict:
        tid, value = self.server_token(TOKEN_BACKUP, PERM_R2_BUCKET,
                                       {f"com.cloudflare.edge.r2.bucket.{self.account}_default_{BUCKET}": "*"})
        secret = hashlib.sha256(value.encode()).hexdigest()
        mask(secret)
        return {"RESTIC_REPOSITORY": f"s3:https://{self.account}.r2.cloudflarestorage.com/{BUCKET}",
                "AWS_ACCESS_KEY_ID": tid, "AWS_SECRET_ACCESS_KEY": secret, "AWS_DEFAULT_REGION": "auto"}

    def invites_token(self) -> str:
        return self.server_token(TOKEN_INVITES, PERM_ACCESS_GROUPS,
                                 {f"com.cloudflare.api.account.{self.account}": "*"})[1]


# ------------------------------------------------------------------------------------------ DigitalOcean
class DigitalOcean:
    def __init__(self, http: Http, sleep=time.sleep):
        self.http, self.sleep = http, sleep

    def registry(self, apply: bool) -> str | None:
        status, out = self.http.send("GET", "/v2/registry")
        if status == 200:
            return out["registry"]["name"]
        if not apply:
            log("would create the container registry")
            return None
        for name in (REGISTRY, f"{REGISTRY}-{os.urandom(3).hex()}"):
            status, out = self.http.send("POST", "/v2/registry",
                                         {"name": name, "subscription_tier_slug": "starter", "region": REGION})
            if status in (200, 201):
                log("created the container registry")
                return out["registry"]["name"]
        raise ProvisionError(f"could not create the container registry: {json.dumps(out)[:300]}")

    def pull_credentials(self) -> str:
        """Docker config.json that can only pull from our registry."""
        out = self.http("GET", "/v2/registry/docker-credentials?read_write=false")
        for reg in out.get("auths", {}).values():
            mask(reg.get("auth", ""))
        return json.dumps(out)

    def volume(self, apply: bool) -> str | None:
        vols = self.http("GET", f"/v2/volumes?name={VOLUME}&region={REGION}").get("volumes", [])
        if vols:
            return vols[0]["id"]
        if not apply:
            log(f"would create the {VOLUME_GB} GB data volume")
            return None
        v = self.http("POST", "/v2/volumes", {"name": VOLUME, "region": REGION, "size_gigabytes": VOLUME_GB,
                                              "description": "LACUNA workspace (/data)", "tags": [TAG]})
        log(f"created the {VOLUME_GB} GB data volume")
        return v["volume"]["id"]

    def firewall(self, apply: bool) -> None:
        fws = self.http("GET", "/v2/firewalls?per_page=200").get("firewalls", [])
        body = {"name": FIREWALL, "inbound_rules": [], "tags": [TAG], "outbound_rules": [
            {"protocol": p, "ports": "all" if p != "icmp" else None,
             "destinations": {"addresses": ["0.0.0.0/0", "::/0"]}} for p in ("tcp", "udp", "icmp")]}
        for r in body["outbound_rules"]:
            if r["ports"] is None:
                del r["ports"]
        fw = next((f for f in fws if f["name"] == FIREWALL), None)
        if not apply:
            log("firewall: " + ("ok" if fw else "would be created (no inbound ports)"))
        elif fw is None:
            self.http("POST", "/v2/firewalls", body)
            log("created the firewall (no inbound ports)")
        elif fw.get("inbound_rules"):
            self.http("PUT", f"/v2/firewalls/{fw['id']}", body)
            log("removed inbound rules from the firewall")

    def size(self) -> str:
        """The first of SIZE + fallbacks that this region offers right now."""
        sizes = {z["slug"]: z for z in self.http("GET", "/v2/sizes?per_page=200").get("sizes", [])}
        for slug in dict.fromkeys((SIZE, *SIZE_FALLBACKS)):
            z = sizes.get(slug)
            if z and z.get("available", True) and REGION in z.get("regions", []):
                log(f"server size: {slug}")
                return slug
        offered = sorted(k for k, z in sizes.items() if REGION in z.get("regions", []) and z.get("vcpus") == 4)
        raise ProvisionError(f"no 4 vCPU / 8 GB size is offered in {REGION} now (4 vCPU sizes there: {offered})")

    def droplets(self) -> list[dict]:
        return self.http("GET", f"/v2/droplets?tag_name={TAG}").get("droplets", [])

    def wait_action(self, droplet_id: int, action_id: int, timeout: float = 600) -> None:
        end = time.time() + timeout
        while time.time() < end:
            a = self.http("GET", f"/v2/droplets/{droplet_id}/actions/{action_id}")["action"]
            if a["status"] == "completed":
                return
            if a["status"] == "errored":
                raise ProvisionError("droplet action failed")
            self.sleep(5)
        raise ProvisionError("droplet action timed out")

    def remove(self, droplet: dict) -> None:
        """Shut the server down cleanly (the app saves on exit), then delete it; the volume stays."""
        did = droplet["id"]
        if droplet.get("status") == "active":
            a = self.http("POST", f"/v2/droplets/{did}/actions", {"type": "shutdown"})["action"]
            try:
                self.wait_action(did, a["id"], timeout=180)
            except ProvisionError:
                a = self.http("POST", f"/v2/droplets/{did}/actions", {"type": "power_off"})["action"]
                self.wait_action(did, a["id"])
        self.http("DELETE", f"/v2/droplets/{did}")
        for _ in range(60):
            if not any(d["id"] == did for d in self.droplets()):
                break
            self.sleep(5)
        log("removed the old server (data volume kept)")

    def create(self, user_data: str, volume_id: str, size: str = SIZE) -> None:
        for _ in range(60):     # the volume must be free (detached from a deleted server)
            v = self.http("GET", f"/v2/volumes/{volume_id}")["volume"]
            if not v.get("droplet_ids"):
                break
            self.sleep(5)
        out = self.http("POST", "/v2/droplets", {
            "name": NAME, "region": REGION, "size": size, "image": "ubuntu-24-04-x64", "tags": [TAG],
            "volumes": [volume_id], "monitoring": True, "ipv6": False, "backups": False, "user_data": user_data})
        did = out["droplet"]["id"]
        for _ in range(120):
            if self.http("GET", f"/v2/droplets/{did}")["droplet"]["status"] == "active":
                break
            self.sleep(5)
        log("created the server; it finishes setting itself up in a few minutes")


# ------------------------------------------------------------------------------------------ cloud-init
def env_file(values: dict) -> str:
    out = []
    for k, v in values.items():
        v = str(v)
        if "\n" in v or "\r" in v:
            raise ProvisionError(f"{k} must be one line")
        out.append(f"{k}={v}")
    return "\n".join(out) + "\n"


def cloud_init(files: dict[str, tuple[str, str]], host_dir: Path = HERE / "host") -> str:
    """#cloud-config: secrets as root-only files, host scripts from deploy/host/, then the bootstrap."""
    entries = []
    for path, (content, mode) in files.items():
        entries.append({"path": path, "permissions": mode, "owner": "root:root",
                        "encoding": "b64", "content": base64.b64encode(content.encode()).decode()})
    for f in sorted(host_dir.iterdir()):
        if f.is_file():
            dest = {".service": "/etc/systemd/system/", ".timer": "/etc/systemd/system/"}.get(f.suffix, "/usr/local/bin/")
            entries.append({"path": dest + f.name, "permissions": "0644" if dest.startswith("/etc") else "0755",
                            "owner": "root:root", "encoding": "b64",
                            "content": base64.b64encode(f.read_bytes()).decode()})
    doc = {"package_update": True, "package_upgrade": True, "write_files": entries,
           "runcmd": [["/usr/local/bin/lacuna-bootstrap"]]}
    return "#cloud-config\n" + json.dumps(doc)    # JSON is valid YAML


def emails_from(raw: str) -> list[str]:
    out = []
    for e in raw.replace(";", ",").replace("\n", ",").split(","):
        e = e.strip().lower()
        if e and "@" in e and e not in out:
            out.append(e)
    return out


def need(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise ProvisionError(f"GitHub secret {name} is missing")
    mask(v)
    return v


def run(mode: str, cf: Cloudflare, do: DigitalOcean) -> dict:
    apply = mode in ("apply", "recreate")
    if apply:      # every secret up front, so a missing one stops the run before anything is created
        for name in ("BACKUP_PASSWORD", "ANTHROPIC_API_KEY", "RESEND_API_KEY"):
            need(name)
    emails = emails_from(need("ACCESS_EMAILS"))
    if not emails:
        raise ProvisionError("ACCESS_EMAILS has no email address")
    for e in emails:
        mask(e)

    team = cf.team_domain()
    tunnel_id, tunnel_token = cf.tunnel(apply)
    cf.dns(tunnel_id, apply)
    idp = cf.one_time_pin(apply)
    group = cf.group(emails, apply)
    aud = cf.application(group, idp, apply)
    cf.bucket(apply)
    registry = do.registry(apply)
    volume = do.volume(apply)
    do.firewall(apply)
    size = do.size()

    servers = do.droplets()
    if len(servers) > 1:
        raise ProvisionError("more than one server is tagged lacuna; remove the extra one in DigitalOcean")
    build = apply and (not servers or mode == "recreate")
    if not build:
        log("server: " + ("ok" if servers else "would be created"))
        return {"registry": registry, "server": bool(servers)}

    app_env = {"LACUNA_CLOUD": "1", "CF_ACCESS_TEAM_DOMAIN": team, "CF_ACCESS_AUD": aud,
               "CF_ACCOUNT_ID": cf.account, "CF_ACCESS_GROUP_ID": group, "CF_ACCESS_API_TOKEN": cf.invites_token(),
               "LACUNA_PUBLIC_URL": f"https://{DOMAIN}", "LACUNA_OWNER_EMAIL": emails[0], "ANTHROPIC_API_KEY": need("ANTHROPIC_API_KEY"),
               "RESEND_API_KEY": need("RESEND_API_KEY")}
    backup_env = cf.backup_credentials() | {"RESTIC_PASSWORD": need("BACKUP_PASSWORD")}
    files = {
        "/etc/lacuna/lacuna.env": (env_file(app_env), "0600"),
        "/etc/lacuna/tunnel.env": (env_file({"TUNNEL_TOKEN": tunnel_token}), "0600"),
        "/etc/lacuna/backup.env": (env_file(backup_env), "0600"),
        "/etc/lacuna/image": (f"registry.digitalocean.com/{registry}/{REPO_IMAGE}:main\n", "0644"),
        "/root/.docker/config.json": (do.pull_credentials(), "0600"),
    }
    user_data = cloud_init(files)
    if len(user_data.encode()) > 64 * 1024:
        raise ProvisionError("cloud-init is over DigitalOcean's 64 KiB limit")
    if servers:
        do.remove(servers[0])
    do.create(user_data, volume, size)
    return {"registry": registry, "server": True}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    mode = argv[0] if argv else "plan"
    if mode not in ("plan", "apply", "recreate"):
        print(__doc__)
        return 2
    try:
        cf = Cloudflare(Http("https://api.cloudflare.com/client/v4", need("CLOUDFLARE_API_TOKEN")))
        do = DigitalOcean(Http("https://api.digitalocean.com", need("DIGITALOCEAN_TOKEN")))
        out = run(mode, cf, do)
    except ProvisionError as e:
        print(f"::error::{e}" if os.environ.get("GITHUB_ACTIONS") == "true" else f"error: {e}", flush=True)
        return 1
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out and out.get("registry"):
        with open(gh_out, "a") as f:
            f.write(f"registry={out['registry']}\n")
    log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
