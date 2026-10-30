"""deploy/provision.py against fake Cloudflare + DigitalOcean APIs: plan changes nothing, apply builds
everything once, a second apply is a no-op, recreate swaps only the server, nothing secret is printed."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy"))
import provision  # noqa: E402

sys.path.pop(0)

SECRETS = {"ACCESS_EMAILS": "Leon@Example.com, pei@example.com", "BACKUP_PASSWORD": "restic-pw-123456",
           "ANTHROPIC_API_KEY": "sk-ant-secret", "RESEND_API_KEY": "re_secret"}


class FakeAPI:
    """Just enough of both APIs, with an id counter and a log of writes."""

    def __init__(self):
        self.n = 0
        self.writes: list[tuple[str, str]] = []
        self.tunnels, self.dns, self.idps, self.groups, self.policies, self.apps = [], [], [], [], [], []
        self.buckets, self.tokens = [], []
        self.widgets: list[dict] = []
        self.turnstile_allowed = True
        self.registry, self.volumes, self.firewalls, self.droplets = None, [], [], []
        self.sizes = [{"slug": "s-4vcpu-8gb", "available": True, "regions": ["sfo3"], "vcpus": 4}]

    def id(self):
        self.n += 1
        return f"id{self.n}"

    def cf(self, method, path, body=None):
        if method != "GET":
            self.writes.append((method, path))
        p = path.split("?")[0]
        ok = lambda r: (200, {"success": True, "result": r})
        if p == "/zones":
            return ok([{"id": "zone1", "account": {"id": "acc1"}}])
        if p.endswith("/access/organizations"):
            return ok({"auth_domain": "lacunastudio.cloudflareaccess.com"})
        if p.endswith("/cfd_tunnel") and method == "GET":
            return ok(self.tunnels)
        if p.endswith("/cfd_tunnel"):
            t = {"id": self.id(), "name": body["name"]}
            self.tunnels.append(t)
            return ok(t)
        if p.endswith("/configurations"):
            self.ingress = body["config"]["ingress"]
            return ok({})
        if p.endswith("/token"):
            return ok("tunnel-token-secret")
        if p.endswith("/dns_records") and method == "GET":
            name = path.split("name=", 1)[1] if "name=" in path else None
            return ok([r for r in self.dns if name is None or r["name"] == name])
        if p.endswith("/dns_records"):
            self.dns.append(body | {"id": self.id()})
            return ok(body)
        if "/dns_records/" in p:
            return ok(body)
        for coll, name in ((self.idps, "identity_providers"), (self.groups, "groups"),
                           (self.policies, "policies"), (self.apps, "apps")):
            if p.endswith(f"/access/{name}"):
                if method == "GET":
                    return ok(coll)
                n = self.id()
                item = body | {"id": n, "aud": "aud-xyz" if name != "apps" or not self.apps else f"aud-{n}"}
                coll.append(item)
                return ok(item)
            if re.search(f"/access/{name}/[^/]+$", p) and method == "DELETE":
                coll[:] = [x for x in coll if x["id"] != p.rsplit("/", 1)[1]]
                return ok({})
            if re.search(f"/access/{name}/[^/]+$", p):
                item = next(x for x in coll if x["id"] == p.rsplit("/", 1)[1])
                item.update(body)
                return ok(item)
        if "/challenges/widgets" in p:
            if not self.turnstile_allowed:
                return 403, {"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]}
            if p.endswith("/challenges/widgets"):
                if method == "GET":
                    return ok([{k: v for k, v in w.items() if k != "secret"} for w in self.widgets])
                w = body | {"sitekey": f"0x4AAA{self.id()}", "secret": f"0x4BBB-turnstile-secret-{self.n}"}
                self.widgets.append(w)
                return ok(w)
            return ok(next(w for w in self.widgets if w["sitekey"] == p.rsplit("/", 1)[1]))
        if p.endswith("/r2/buckets"):
            if method == "GET":
                return ok({"buckets": [{"name": b} for b in self.buckets]})
            self.buckets.append(body["name"])
            return ok({})
        if p == "/user/tokens/permission_groups":
            return ok([{"id": "pg-r2", "name": provision.PERM_R2_BUCKET},
                       {"id": "pg-r2-read", "name": provision.PERM_R2_READ},
                       {"id": "pg-acc", "name": provision.PERM_ACCESS_GROUPS}])
        if p == "/user/tokens":
            if method == "GET":
                return ok(self.tokens)
            t = {"id": self.id(), "name": body["name"], "value": f"token-value-{self.n}",
                 "perm": body["policies"][0]["permission_groups"][0]["id"], "resources": body["policies"][0]["resources"]}
            self.tokens.append(t)
            return ok(t)
        if p.startswith("/user/tokens/"):
            self.tokens = [t for t in self.tokens if t["id"] != p.rsplit("/", 1)[1]]
            return ok({})
        raise AssertionError(f"unexpected Cloudflare call {method} {path}")

    def do(self, method, path, body=None):
        if method != "GET":
            self.writes.append((method, path))
        p = path.split("?")[0]
        if p == "/v2/registry":
            if method == "GET":
                return (200, {"registry": self.registry}) if self.registry else (404, {})
            self.registry = {"name": body["name"]}
            self.tier = body["subscription_tier_slug"]
            return 201, {"registry": self.registry}
        if p == "/v2/registry/subscription":
            if method == "POST":
                self.tier = body["tier_slug"]
            return 200, {"subscription": {"tier": {"slug": self.tier}}}
        if p == "/v2/registry/docker-credentials":
            return 200, {"auths": {"registry.digitalocean.com": {"auth": "pull-cred-secret"}}}
        if p == "/v2/volumes":
            if method == "GET":
                return 200, {"volumes": self.volumes}
            v = {"id": self.id(), "droplet_ids": [], "size_gigabytes": body["size_gigabytes"]}
            self.volumes.append(v)
            return 201, {"volume": v}
        if re.fullmatch(r"/v2/volumes/[^/]+/actions", p):
            v = next(v for v in self.volumes if v["id"] == p.split("/")[3])
            assert body["type"] == "resize" and body["size_gigabytes"] > v.get("size_gigabytes", 0)
            v["size_gigabytes"] = body["size_gigabytes"]
            return 201, {"action": {"id": 7, "status": "in-progress"}}
        if p.startswith("/v2/volumes/"):
            return 200, {"volume": {"droplet_ids": []}}
        if p == "/v2/firewalls":
            if method == "GET":
                return 200, {"firewalls": self.firewalls}
            self.firewalls.append(body)
            return 202, {}
        if p == "/v2/sizes":
            return 200, {"sizes": self.sizes}
        if p == "/v2/droplets":
            if method == "GET":
                return 200, {"droplets": self.droplets}
            d = {"id": len(self.droplets) + 100 + self.n, "status": "active", "user_data": body["user_data"],
                 "size": body["size"]}
            self.n += 1
            self.droplets.append(d)
            return 202, {"droplet": d}
        if re.fullmatch(r"/v2/droplets/\d+/actions", p):
            return 201, {"action": {"id": 1, "status": "completed"}}
        if re.fullmatch(r"/v2/droplets/\d+/actions/\d+", p):
            return 200, {"action": {"status": "completed"}}
        if re.fullmatch(r"/v2/droplets/\d+", p):
            did = int(p.rsplit("/", 1)[1])
            if method == "DELETE":
                self.droplets = [d for d in self.droplets if d["id"] != did]
                return 204, {}
            return 200, {"droplet": next(d for d in self.droplets if d["id"] == did)}
        raise AssertionError(f"unexpected DigitalOcean call {method} {path}")


class FakeHttp(provision.Http):
    def __init__(self, handler):
        super().__init__("", "t")
        self.handler = handler

    def send(self, method, path, body=None):
        return self.handler(method, path, json.loads(json.dumps(body)) if body is not None else None)


@pytest.fixture
def api(monkeypatch):
    # on GitHub the ::add-mask:: lines are swallowed by the runner; here they would print the values
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    for k, v in SECRETS.items():
        monkeypatch.setenv(k, v)
    a = FakeAPI()

    def run(mode, door="access"):
        cf = provision.Cloudflare(FakeHttp(a.cf))
        do = provision.DigitalOcean(FakeHttp(a.do), sleep=lambda s: None)
        return provision.run(mode, cf, do, door)

    return a, run


def user_data(a):
    doc = json.loads(a.droplets[0]["user_data"].split("\n", 1)[1])
    import base64
    return {f["path"]: base64.b64decode(f["content"]).decode() for f in doc["write_files"]}


def test_plan_changes_nothing(api):
    a, run = api
    run("plan")
    assert a.writes == []


def test_apply_builds_everything_once(api, capsys):
    a, run = api
    run("apply")
    assert len(a.tunnels) == 1 and len(a.dns) == 3 and all(r["proxied"] for r in a.dns)
    assert {r["content"] for r in a.dns} == {f"{a.tunnels[0]['id']}.cfargotunnel.com"}
    assert [i["type"] for i in a.idps] == ["onetimepin"]
    assert [r["email"]["email"] for r in a.groups[0]["include"]] == ["leon@example.com", "pei@example.com"]
    assert a.apps[0]["domain"] == provision.DOMAIN and len(a.apps[0]["policies"]) == 2
    assert a.apps[1]["domain"] == provision.PREVIEW_DOMAIN and a.apps[1]["policies"] == a.apps[0]["policies"]
    # no path is open to everyone any more (the public /api/version was withdrawn)
    assert [x["domain"] for x in a.apps] == [provision.DOMAIN, provision.PREVIEW_DOMAIN, provision.ADMIN_DOMAIN]
    assert not [p for p in a.policies if p["decision"] == "bypass"]
    assert a.buckets == [provision.BUCKET, provision.AUDIO_BUCKET] and a.registry and len(a.volumes) == 1
    assert a.volumes[0]["size_gigabytes"] == 100
    assert a.firewalls[0]["inbound_rules"] == []
    assert len(a.droplets) == 1
    files = user_data(a)
    env = files["/etc/lacuna/lacuna.env"]
    assert "LACUNA_CLOUD=1" in env and "CF_ACCESS_AUD=aud-xyz" in env and "ANTHROPIC_API_KEY=sk-ant-secret" in env
    assert "CF_ACCESS_TEAM_DOMAIN=lacunastudio.cloudflareaccess.com" in env
    assert "LACUNA_OWNER_EMAIL=leon@example.com" in env
    assert f"LACUNA_AUDIO_STORE=https://acc1.r2.cloudflarestorage.com/{provision.AUDIO_BUCKET}" in env
    audio = next(t for t in a.tokens if t["name"] == provision.TOKEN_AUDIO)
    assert audio["perm"] == "pg-r2" and list(audio["resources"]) == [f"com.cloudflare.edge.r2.bucket.acc1_default_{provision.AUDIO_BUCKET}"]
    assert f"LACUNA_AUDIO_KEY_ID={audio['id']}" in env
    assert "TUNNEL_TOKEN=tunnel-token-secret" in files["/etc/lacuna/tunnel.env"]
    assert "RESTIC_PASSWORD=restic-pw-123456" in files["/etc/lacuna/backup.env"]
    assert "registry.digitalocean.com" in files["/etc/lacuna/image"]
    out = capsys.readouterr().out
    for secret in ("sk-ant-secret", "re_secret", "restic-pw", "tunnel-token-secret", "pull-cred-secret",
                   "token-value", "leon@example.com"):
        assert secret not in out

    before = len(a.writes)
    a.writes.clear()
    run("apply")
    creates = [w for w in a.writes if w[0] in ("POST", "DELETE")]
    assert creates == [], creates             # second run: only idempotent PUTs, same server
    assert len(a.droplets) == 1 and before


def test_staging_site_has_its_own_address_door_and_data(api):
    """decision staging-site: same server, same invite list, its own Access audience, no Access token"""
    a, run = api
    run("apply")
    assert {r["name"] for r in a.dns} == {provision.DOMAIN, provision.PREVIEW_DOMAIN, provision.ADMIN_DOMAIN}
    routes = {r.get("hostname"): r["service"] for r in a.ingress}
    assert routes[provision.DOMAIN] == "http://lacuna:8765"
    assert routes[provision.PREVIEW_DOMAIN] == "http://lacuna-preview:8765"
    assert routes[None] == "http_status:404"
    files = user_data(a)
    real, staging = files["/etc/lacuna/lacuna.env"], files["/etc/lacuna/preview.env"]
    env = dict(line.split("=", 1) for line in staging.splitlines())
    assert env["CF_ACCESS_AUD"] == a.apps[1]["aud"] != a.apps[0]["aud"]
    assert env["LACUNA_PUBLIC_URL"] == f"https://{provision.PREVIEW_DOMAIN}" and env["LACUNA_STAGING"] == "1"
    assert "CF_ACCESS_API_TOKEN" not in env and "CF_ACCESS_API_TOKEN=" in real and "LACUNA_STAGING" not in real
    assert "LACUNA_ADMIN_HOST" not in env and "CF_ADMIN_ACCESS_AUD" not in env     # no admin on staging
    # staging reads old episodes' audio from cloud storage with its own read-only token, and never moves any
    read = next(t for t in a.tokens if t["name"] == provision.TOKEN_AUDIO_READ)
    assert read["perm"] == "pg-r2-read" and env["LACUNA_AUDIO_KEY_ID"] == read["id"]
    assert files["/etc/lacuna/preview-image"].strip().endswith("/lacuna:preview")
    assert "/etc/systemd/system/lacuna-update-preview.timer" in files
    unit = files["/etc/systemd/system/lacuna-update-preview.service"]
    assert "LACUNA_DATA=/data/preview" in unit and "LACUNA_SEED_FROM=/data/workspace" in unit
    assert "--exclude /data/preview" in files["/usr/local/bin/lacuna-backup"]


def test_admin_site_lets_in_only_the_owner(api):
    """decision admin-site: admin.<domain> goes to the real container behind its own Access application:
    the first ACCESS_EMAILS address only, 8-hour sessions, no service tokens, no public paths"""
    a, run = api
    run("apply")
    routes = {r.get("hostname"): r["service"] for r in a.ingress}
    assert routes[provision.ADMIN_DOMAIN] == "http://lacuna:8765"
    app = next(x for x in a.apps if x["domain"] == provision.ADMIN_DOMAIN)
    assert app["name"] == provision.ADMIN_APP and app["session_duration"] == "8h"
    assert [x["domain"] for x in a.apps if x["domain"].startswith(provision.ADMIN_DOMAIN)] == [provision.ADMIN_DOMAIN]
    pols = [next(p for p in a.policies if p["id"] == x["id"]) for x in app["policies"]]
    assert [(p["decision"], p["include"]) for p in pols] == [("allow", [{"email": {"email": "leon@example.com"}}])]
    env = dict(line.split("=", 1) for line in user_data(a)["/etc/lacuna/lacuna.env"].splitlines())
    assert env["LACUNA_ADMIN_HOST"] == provision.ADMIN_DOMAIN
    assert env["CF_ADMIN_ACCESS_AUD"] == app["aud"] != env["CF_ACCESS_AUD"]
    # an admin the owner added by hand in Cloudflare stays on the list when Provision runs again (batch 8)
    pol = next(p for p in a.policies if p["name"] == provision.ADMIN_POLICY)
    pol["include"].append({"email": {"email": "pei@example.com"}})
    run("apply")
    pol = next(p for p in a.policies if p["name"] == provision.ADMIN_POLICY)
    assert pol["include"] == [{"email": {"email": "leon@example.com"}}, {"email": {"email": "pei@example.com"}}]


def test_registry_gc_keeps_the_site_and_staging_images(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy"))
    import ci
    sys.path.pop(0)
    deleted = []

    def doh(method, path, body=None):
        p = path.split("?")[0]
        if p == "/v2/registry":
            return 200, {"registry": {"name": "reg"}}
        if p == "/v2/registry/subscription":
            return 200, {"subscription": {"tier": {"slug": "basic"}}}
        if p.endswith("/tags") and method == "GET":
            tags = ["main", "preview", "s5", "s4", "s3", "s2", "s1"]
            return 200, {"tags": [{"tag": t, "updated_at": f"2026-10-{19 - i:02d}"} for i, t in enumerate(tags)]}
        if "/tags/" in p:
            deleted.append(p.rsplit("/", 1)[1])
            return 204, {}
        raise AssertionError(path)     # no garbage collection here: it makes the registry read-only

    monkeypatch.setattr(ci, "do", lambda: provision.DigitalOcean(FakeHttp(doh)))
    ci.registry_gc()
    assert deleted == ["s2", "s1"]          # main, preview and the three newest builds stay


def test_weekly_snapshot_on_a_new_volume_without_snapshots(monkeypatch, capsys):
    ci = _ci()
    calls = []

    def doh(method, path, body=None):
        calls.append((method, path.split("?")[0]))
        if path.startswith("/v2/volumes?"):
            return 200, {"volumes": [{"id": "v1"}]}
        if path.startswith("/v2/volumes/v1/snapshots") and method == "POST":
            return 201, {"snapshot": {"id": "s1"}}
        if path.startswith("/v2/volumes/v1/snapshots"):
            return 200, {"snapshots": None, "links": {}, "meta": {"total": 0}}
        raise AssertionError(path)

    monkeypatch.setattr(ci, "do", lambda: provision.DigitalOcean(FakeHttp(doh)))
    assert ci.main(["snapshot"]) == 0
    assert ("POST", "/v2/volumes/v1/snapshots") in calls and not any(m == "DELETE" for m, _ in calls)
    assert "snapshot taken" in capsys.readouterr().out


def test_pushes_wait_for_a_running_garbage_collection(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy"))
    import ci
    sys.path.pop(0)
    states = ["scanning manifests", "deleting unreferenced blobs", None]
    calls = []

    def doh(method, path, body=None):
        p = path.split("?")[0]
        if p == "/v2/registry":
            return 200, {"registry": {"name": "reg"}}
        if p == "/v2/registry/subscription":
            return 200, {"subscription": {"tier": {"slug": "basic"}}}
        if p.endswith("/garbage-collection") and method == "GET":
            s = states.pop(0)
            return (200, {"garbage_collection": {"status": s}}) if s else (404, {})
        if p.endswith("/garbage-collection") and method == "POST":
            calls.append("collect")
            return 201, {}
        raise AssertionError(path)

    monkeypatch.setattr(ci.time, "sleep", lambda s: None)
    d = provision.DigitalOcean(FakeHttp(doh))
    ci.wait_gc(d, "reg")
    assert states == []                   # asked until none was running
    states[:] = ["requested"]
    with pytest.raises(provision.ProvisionError):
        ci.wait_gc(d, "reg", timeout=-1)
    monkeypatch.setattr(ci, "do", lambda: d)
    states[:] = [None]
    ci.registry_collect()
    assert calls == ["collect"]


def test_apply_keeps_people_invited_in_the_app(api):
    a, run = api
    run("apply")
    a.groups[0]["include"].append({"email": {"email": "guest@example.com"}})
    run("apply")
    assert "guest@example.com" in [r["email"]["email"] for r in a.groups[0]["include"]]


def test_recreate_replaces_only_the_server_and_rotates_its_tokens(api):
    a, run = api
    run("apply")
    first = a.droplets[0]["id"]
    old_tokens = {t["id"] for t in a.tokens}
    run("recreate")
    assert len(a.droplets) == 1 and a.droplets[0]["id"] != first
    assert len(a.volumes) == 1 and len(a.tunnels) == 1
    assert len(a.tokens) == 4 and not old_tokens & {t["id"] for t in a.tokens}


def test_missing_secret_is_named(api, monkeypatch):
    a, run = api
    monkeypatch.delenv("BACKUP_PASSWORD")
    with pytest.raises(provision.ProvisionError, match="BACKUP_PASSWORD"):
        run("apply")


def test_apply_removes_the_old_public_version_address(api, monkeypatch):
    """decision 2026-10-25-withdraw-public-version: the two path-scoped Access apps and their bypass policy go;
    close-version-door does only that"""
    a, run = api
    bypass = {"id": "polv", "name": provision.VERSION_POLICY, "decision": "bypass", "include": [{"everyone": {}}]}
    olds = [{"id": f"v{i}", "name": f"{n} version", "domain": f"{d}/api/version", "policies": [{"id": "polv"}]}
            for i, (n, d) in enumerate(((provision.ACCESS_APP, provision.DOMAIN), (provision.PREVIEW_APP, provision.PREVIEW_DOMAIN)))]
    a.policies.append(dict(bypass))
    a.apps.extend(dict(o) for o in olds)
    run("plan")
    assert len(a.apps) == 2 and a.writes == []                     # plan only says so
    run("apply")
    assert not [x for x in a.apps if x["domain"].endswith("/api/version")]
    assert not [p for p in a.policies if p["name"] == provision.VERSION_POLICY]
    # the mode that does only this, patient with Cloudflare's API
    a2 = FakeAPI()
    a2.policies.append(dict(bypass))
    a2.apps.extend(dict(o) for o in olds)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    monkeypatch.setattr(provision.Http, "send", lambda self, m, p, b=None: a2.cf(m, p, b))
    assert provision.main(["close-version-door"]) == 0
    assert a2.apps == [] and a2.policies == [] and not a2.droplets and not a2.tunnels


def test_an_older_smaller_volume_is_grown_in_place(api):
    a, run = api
    a.volumes.append({"id": "vol1", "droplet_ids": [], "size_gigabytes": 50})
    run("plan")
    assert a.volumes[0]["size_gigabytes"] == 50
    run("apply")
    assert a.volumes == [{"id": "vol1", "droplet_ids": [], "size_gigabytes": 100}]
    assert "resize2fs" in (Path(__file__).resolve().parent.parent / "deploy" / "host" / "lacuna-bootstrap").read_text()


def test_deploy_token_is_printed_only_sealed(api, monkeypatch, capsys):
    a, _ = api
    tokens = []

    def cfh(method, path, body=None):
        p = path.split("?")[0]
        if p == "/zones":
            return 200, {"success": True, "result": [{"id": "z", "account": {"id": "acc"}}]}
        if p.endswith("/service_tokens") and method == "GET":
            return 200, {"success": True, "result": list(tokens)}
        if p.endswith("/service_tokens") and method == "POST":
            assert body["name"] == provision.DEPLOY_TOKEN
            t = {"id": "st1", "name": body["name"], "client_id": "cid-1.access"}
            tokens.append(t)
            return 200, {"success": True, "result": t | {"client_secret": "first-secret"}}
        if p.endswith("/st1/rotate"):
            return 200, {"success": True, "result": {"client_id": "cid-1.access", "client_secret": "second-secret"}}
        raise AssertionError(f"{method} {path}")

    monkeypatch.setenv("GH_SECRETS_KEY", "pubkey")
    monkeypatch.setenv("GH_SECRETS_KEY_ID", "kid1")
    cf = provision.Cloudflare(FakeHttp(cfh))
    sealer = lambda key, v: f"sealed[{key}]({v[::-1]})"          # noqa: E731 - stands in for the sealed box
    out = provision.deploy_token_sealed(cf, sealer)
    assert out["CF_DEPLOY_CLIENT_SECRET"] == sealer("pubkey", "first-secret")
    assert provision.deploy_token_sealed(cf, sealer)["CF_DEPLOY_CLIENT_SECRET"] == sealer("pubkey", "second-secret")
    assert len(tokens) == 1                                       # made once, then rotated
    printed = capsys.readouterr().out
    assert "first-secret" not in printed and "second-secret" not in printed and "cid-1.access" not in printed
    monkeypatch.delenv("GH_SECRETS_KEY")
    with pytest.raises(provision.ProvisionError, match="GH_SECRETS_KEY"):
        provision.deploy_token_sealed(cf, sealer)


def _ci():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy"))
    import ci
    sys.path.pop(0)
    return ci


def test_ci_wait_live_reads_health_through_access_with_the_deploy_token(monkeypatch):
    ci = _ci()
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    monkeypatch.setenv("CF_DEPLOY_CLIENT_ID", "cid.access")
    monkeypatch.setenv("CF_DEPLOY_CLIENT_SECRET", "sec")
    tokens = [{"id": "old1", "name": "lacuna-deploy-check-1"}, {"id": "keep", "name": provision.DEPLOY_TOKEN}]

    def cfh(method, path, body=None):
        p = path.split("?")[0]
        if p == "/zones":
            return 200, {"success": True, "result": [{"id": "z", "account": {"id": "acc"}}]}
        if p.endswith("/service_tokens") and method == "GET":
            return 200, {"success": True, "result": list(tokens)}
        if "/service_tokens/" in p and method == "DELETE":
            tokens[:] = [t for t in tokens if t["id"] != p.rsplit("/", 1)[1]]
            return 200, {"success": True, "result": {}}
        raise AssertionError(f"{method} {path}")       # never creates a token when the secret is there

    monkeypatch.setattr(ci, "cf", lambda: provision.Cloudflare(FakeHttp(cfh)))
    monkeypatch.setattr(ci.time, "sleep", lambda s: None)
    answers = iter([(403, {}), (200, {"version": "old"}), (200, {"version": "abc"})])
    seen = []
    monkeypatch.setattr(ci, "_get", lambda url, h: (seen.append((url, h)), next(answers))[1])
    ci.wait_live("abc")
    assert seen[-1] == (f"https://{provision.DOMAIN}/api/health",
                        {"CF-Access-Client-Id": "cid.access", "CF-Access-Client-Secret": "sec"})
    assert tokens == [{"id": "keep", "name": provision.DEPLOY_TOKEN}]     # leftovers deleted, the long-lived one kept
    answers = iter([(200, {"version": "abc"})])
    assert ci.main(["wait-live", "abc", "preview"]) == 0 and seen[-1][0] == f"https://{provision.PREVIEW_DOMAIN}/api/health"

    monkeypatch.setattr(ci, "_get", lambda url, h: (200, {"version": "old"}))
    with pytest.raises(provision.ProvisionError, match="not live"):
        ci.wait_live("abc", timeout=0.01, poll=0)

    def down(method, path, body=None):                 # Cloudflare's API failing never fails a live deploy
        return (200, {"success": True, "result": [{"id": "z", "account": {"id": "acc"}}]}) if path.startswith("/zones") \
            else (504, {"raw": "error code: 504"})
    monkeypatch.setattr(ci, "cf", lambda: provision.Cloudflare(FakeHttp(down)))
    monkeypatch.setattr(provision.Http, "RETRY_WAITS", ())
    monkeypatch.setattr(ci, "_get", lambda url, h: (200, {"version": "abc"}))
    ci.wait_live("abc")


def test_ci_uptime_fails_only_when_the_site_stays_down(monkeypatch):
    """batch 8, P3: the hourly outside check; GitHub mails the owner when the run fails"""
    ci = _ci()
    monkeypatch.setenv("CF_DEPLOY_CLIENT_ID", "cid.access")
    monkeypatch.setenv("CF_DEPLOY_CLIENT_SECRET", "sec")
    waits = []
    monkeypatch.setattr(ci.time, "sleep", waits.append)
    seen = []
    answers = iter([(502, {}), (200, {"ok": True, "version": "abc"})])
    monkeypatch.setattr(ci, "_get", lambda url, h: (seen.append((url, h)), next(answers))[1])
    assert ci.main(["uptime"]) == 0
    assert seen[-1] == (f"https://{provision.DOMAIN}/api/health",
                        {"CF-Access-Client-Id": "cid.access", "CF-Access-Client-Secret": "sec"})
    assert waits == [ci.UPTIME_WAIT]
    monkeypatch.setattr(ci, "_get", lambda url, h: (0, {}))
    with pytest.raises(provision.ProvisionError, match="is down"):
        ci.uptime()
    assert ci.main(["uptime"]) == 1
    monkeypatch.delenv("CF_DEPLOY_CLIENT_SECRET")      # not provisioned yet: nothing to check, no failure
    assert ci.main(["uptime"]) == 0


def test_ci_wait_live_without_the_secret_uses_a_token_for_this_run(monkeypatch):
    ci = _ci()
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    monkeypatch.delenv("CF_DEPLOY_CLIENT_ID", raising=False)
    monkeypatch.delenv("CF_DEPLOY_CLIENT_SECRET", raising=False)
    monkeypatch.setenv("GITHUB_RUN_ID", "42")
    tokens = []

    def cfh(method, path, body=None):
        p = path.split("?")[0]
        if p == "/zones":
            return 200, {"success": True, "result": [{"id": "z", "account": {"id": "acc"}}]}
        if p.endswith("/service_tokens") and method == "POST":
            t = {"id": "run", "name": body["name"], "client_id": "c.access"}
            tokens.append(t)
            return 200, {"success": True, "result": t | {"client_secret": "s"}}
        if p.endswith("/service_tokens"):
            return 200, {"success": True, "result": list(tokens)}
        if "/service_tokens/" in p and method == "DELETE":
            tokens[:] = [t for t in tokens if t["id"] != p.rsplit("/", 1)[1]]
            return 200, {"success": True, "result": {}}
        raise AssertionError(f"{method} {path}")

    monkeypatch.setattr(ci, "cf", lambda: provision.Cloudflare(FakeHttp(cfh)))
    seen = []
    monkeypatch.setattr(ci, "_get", lambda url, h: (seen.append(h), (200, {"version": "abc"}))[1])
    ci.wait_live("abc")
    assert seen == [{"CF-Access-Client-Id": "c.access", "CF-Access-Client-Secret": "s"}]
    assert tokens == []                                   # this run's token is deleted afterwards


def test_server_size_falls_back_when_the_region_stops_offering_it(api):
    a, run = api
    a.sizes = [{"slug": "s-4vcpu-8gb", "available": True, "regions": ["nyc1"], "vcpus": 4},
               {"slug": "s-4vcpu-8gb-amd", "available": True, "regions": ["sfo3"], "vcpus": 4}]
    run("apply")
    assert a.droplets[0]["size"] == "s-4vcpu-8gb-amd"


def test_no_size_in_the_region_stops_before_creating_the_server(api):
    a, run = api
    a.sizes = [{"slug": "s-4vcpu-8gb", "available": False, "regions": ["sfo3"], "vcpus": 4}]
    with pytest.raises(provision.ProvisionError, match="no 4 vCPU"):
        run("apply")
    assert not a.droplets


def test_registry_on_the_free_plan_moves_to_basic(api):
    a, run = api
    a.registry, a.tier = {"name": "lacunastudio"}, "starter"
    run("plan")
    assert a.tier == "starter"
    run("apply")
    assert a.tier == "basic" and ("POST", "/v2/registry/subscription") in a.writes


def test_api_calls_retry_a_5xx_or_a_dropped_connection():
    """Cloudflare's API sometimes answers 504 (Staging for #143 failed three times on it)."""
    import urllib.error

    answers = [(504, {}), urllib.error.URLError("reset"), (200, {"success": True, "result": {"id": "s1"}})]

    def handler(method, path, body=None):
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a

    waits = []
    h = FakeHttp(handler)
    h.sleep = waits.append
    assert h("POST", "/accounts/a/access/service_tokens", {"name": "x"})["result"]["id"] == "s1"
    assert waits == [5, 15]

    h = FakeHttp(lambda m, p, b=None: (503, {}))
    h.sleep = lambda s: None
    with pytest.raises(provision.ProvisionError, match="503"):
        h("GET", "/x")

    calls = []
    h = FakeHttp(lambda m, p, b=None: (calls.append(1), (403, {"errors": ["no"]}))[1])
    with pytest.raises(provision.ProvisionError, match="403"):
        h("GET", "/x")
    assert len(calls) == 1                   # a 4xx is an answer, not a hiccup


class FakeResend:
    def __init__(self, restricted=False):
        self.domains, self.writes, self.restricted, self.checks = [], [], restricted, 0

    def __call__(self, method, path, body=None):
        if self.restricted:
            return 401, {"name": "restricted_api_key", "message": "This API key is restricted to only send emails"}
        if method != "GET":
            self.writes.append((method, path))
        if path == "/domains":
            if method == "GET":
                return 200, {"data": [{"id": d["id"], "name": d["name"]} for d in self.domains]}
            d = {"id": "dom1", "name": body["name"], "status": "not_started", "records": [
                {"record": "DKIM", "name": "resend._domainkey", "type": "TXT", "value": "p=MIGfMA0"},
                {"record": "SPF", "name": "send", "type": "MX", "value": "feedback-smtp.us-east-1.amazonses.com",
                 "priority": 10},
                {"record": "SPF", "name": "send", "type": "TXT", "value": "v=spf1 include:amazonses.com ~all"},
                {"record": "Receiving", "name": "lacunastudio.app", "type": "MX", "value": "inbound-smtp.resend.com",
                 "priority": 10}]}
            self.domains.append(d)
            return 201, {"id": d["id"]}
        if path == "/domains/dom1/verify":
            self.domains[0]["status"] = "pending"
            return 200, {}
        if path == "/domains/dom1":
            if self.domains[0]["status"] == "pending":
                self.checks += 1
                if self.checks >= 2:
                    self.domains[0]["status"] = "verified"
            return 200, self.domains[0]
        raise AssertionError(f"unexpected Resend call {method} {path}")


def test_mail_domain_adds_resend_records_and_verifies_once(api):
    a, _ = api
    a.dns.append({"id": "old", "type": "CNAME", "name": provision.DOMAIN, "content": "t.cfargotunnel.com"})
    rs = FakeResend()
    cf, resend = provision.Cloudflare(FakeHttp(a.cf)), provision.Resend(FakeHttp(rs))
    assert provision.mail_domain(cf, resend, False) == "missing" and not rs.writes and not a.writes   # plan
    assert provision.mail_domain(cf, resend, True, sleep=lambda s: None) == "verified"
    added = {(r["type"], r["name"]) for r in a.dns if r["id"] != "old"}
    assert added == {("TXT", f"resend._domainkey.{provision.DOMAIN}"), ("MX", f"send.{provision.DOMAIN}"),
                     ("TXT", f"send.{provision.DOMAIN}"), ("TXT", f"_dmarc.{provision.DOMAIN}")}
    assert not any(r.get("proxied") for r in a.dns if r["id"] != "old")       # email records are DNS only
    assert next(r for r in a.dns if r["type"] == "MX")["priority"] == 10
    writes = (len(a.writes), len(rs.writes))
    assert provision.mail_domain(cf, resend, True) == "verified"                # second run changes nothing
    assert (len(a.writes), len(rs.writes)) == writes


def test_mail_domain_names_a_send_only_resend_key():
    rs = FakeResend(restricted=True)
    with pytest.raises(provision.ProvisionError, match="Full access"):
        provision.Resend(FakeHttp(rs)).ensure(True)


# ---- the site door (decision 2026-10-21-app-sign-in): Access off only with recreate, and back again

def _env(a, name="/etc/lacuna/lacuna.env"):
    return dict(line.split("=", 1) for line in user_data(a)[name].splitlines())


def _main_policies(a):
    app = next(x for x in a.apps if x["domain"] == provision.DOMAIN)
    return [next(p for p in a.policies if p["id"] == x["id"]) for x in app["policies"]]


def test_site_door_file_says_access_by_default(tmp_path):
    assert provision.site_door(tmp_path / "none.txt") == "access"
    (tmp_path / "d.txt").write_text("open\n")
    assert provision.site_door(tmp_path / "d.txt") == "open"
    (tmp_path / "d.txt").write_text("wide open")
    with pytest.raises(provision.ProvisionError):
        provision.site_door(tmp_path / "d.txt")
    assert provision.site_door() == "access"      # the repo's file: Access stays until Leon says otherwise


def test_open_door_with_apply_changes_nothing_in_front_of_the_running_server(api, capsys):
    a, run = api
    run("apply")
    before = [dict(p) for p in _main_policies(a)]
    run("apply", door="open")
    assert [p["decision"] for p in _main_policies(a)] == [p["decision"] for p in before] == ["allow", "non_identity"]
    assert a.widgets == []
    assert "takes effect with recreate" in capsys.readouterr().out


def test_open_door_with_recreate_lets_everyone_reach_the_apps_own_sign_in(api, capsys):
    a, run = api
    run("apply")
    run("plan", door="open")
    assert a.widgets == []
    run("recreate", door="open")
    assert [p["decision"] for p in _main_policies(a)] == ["bypass", "non_identity"]
    assert _main_policies(a)[0]["include"] == [{"everyone": {}}]
    staging = next(x for x in a.apps if x["domain"] == provision.PREVIEW_DOMAIN)
    assert next(p for p in a.policies if p["id"] == staging["policies"][0]["id"])["decision"] == "allow"
    admin = next(x for x in a.apps if x["domain"] == provision.ADMIN_DOMAIN)     # the admin never opens
    assert next(p for p in a.policies if p["id"] == admin["policies"][0]["id"])["decision"] == "allow"
    assert len(a.widgets) == 1 and a.widgets[0]["domains"] == [provision.DOMAIN]
    env = _env(a)
    assert env["LACUNA_ACCESS"] == "off" and env["TURNSTILE_SITE_KEY"] == a.widgets[0]["sitekey"]
    assert env["TURNSTILE_SECRET_KEY"] == a.widgets[0]["secret"]
    assert not {"LACUNA_ACCESS", "TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY"} & set(_env(a, "/etc/lacuna/preview.env"))
    assert "turnstile-secret" not in capsys.readouterr().out
    # again: the same widget, not a second one
    run("recreate", door="open")
    assert len(a.widgets) == 1

    # the way back: access + recreate puts Access in front again
    run("recreate", door="access")
    assert [p["decision"] for p in _main_policies(a)] == ["allow", "non_identity"]
    assert "LACUNA_ACCESS" not in _env(a) and "TURNSTILE_SECRET_KEY" not in _env(a)


def test_open_door_without_the_turnstile_permission_stops_before_the_server(api):
    a, run = api
    run("apply")
    a.turnstile_allowed = False
    first = a.droplets[0]["id"]
    with pytest.raises(provision.ProvisionError, match="Turnstile"):
        run("recreate", door="open")
    assert a.droplets[0]["id"] == first
    assert [p["decision"] for p in _main_policies(a)] == ["allow", "non_identity"]


def test_http3_off_turns_only_that_switch_off(capsys):
    calls = []
    state = {"value": "on"}

    def cfh(method, path, body):
        calls.append((method, path.split("?")[0]))
        if path.startswith("/zones?name="):
            return 200, {"success": True, "result": [{"id": "z1", "account": {"id": "a1"}}]}
        if path == "/zones/z1/settings/http3":
            if method == "PATCH":
                assert body == {"value": "off"}
                state["value"] = "off"
            return 200, {"success": True, "result": {"id": "http3", "value": state["value"]}}
        raise AssertionError(f"{method} {path}")

    cf = provision.Cloudflare(FakeHttp(cfh))
    assert cf.http3(False) == "on" and state["value"] == "on"     # check: changes nothing
    assert cf.http3(True) == "off"
    calls.clear()
    assert cf.http3(True) == "off"                                # already off: no PATCH
    assert ("PATCH", "/zones/z1/settings/http3") not in calls
    assert "HTTP/3" in capsys.readouterr().out


def test_ci_perf_prints_slow_routes_and_lock_holders():
    ci = _ci()
    text = ci.perf_text({"up_s": 600, "load1": 1.2, "threads_busy": 3, "in_flight": {},
                         "slow": [{"at": 0, "route": "POST /api/episodes/{ep}/manual/cut", "status": 200, "ttfb": 12.3,
                                   "lock_wait": 11.9, "holders": ["GET /api/episodes/{ep}/audio/{v}.wav"],
                                   "threads_busy_at_start": 40, "load1": 3.9, "in_flight": {}}],
                         "holds": [{"at": 0, "s": 2.1, "by": "GET /api/episodes/{ep}/audio/{v}.wav"}], "lags": []})
    assert "12.30   11.90  POST /api/episodes/{ep}/manual/cut" in text
    assert "held by ['GET /api/episodes/{ep}/audio/{v}.wav']" in text
