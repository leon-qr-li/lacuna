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
            if re.search(f"/access/{name}/[^/]+$", p):
                item = next(x for x in coll if x["id"] == p.rsplit("/", 1)[1])
                item.update(body)
                return ok(item)
        if p.endswith("/r2/buckets"):
            if method == "GET":
                return ok({"buckets": [{"name": b} for b in self.buckets]})
            self.buckets.append(body["name"])
            return ok({})
        if p == "/user/tokens/permission_groups":
            return ok([{"id": "pg-r2", "name": provision.PERM_R2_BUCKET},
                       {"id": "pg-acc", "name": provision.PERM_ACCESS_GROUPS}])
        if p == "/user/tokens":
            if method == "GET":
                return ok(self.tokens)
            t = {"id": self.id(), "name": body["name"], "value": f"token-value-{self.n}"}
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
            v = {"id": self.id(), "droplet_ids": []}
            self.volumes.append(v)
            return 201, {"volume": v}
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

    def run(mode):
        cf = provision.Cloudflare(FakeHttp(a.cf))
        do = provision.DigitalOcean(FakeHttp(a.do), sleep=lambda s: None)
        return provision.run(mode, cf, do)

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
    assert len(a.tunnels) == 1 and len(a.dns) == 2 and all(r["proxied"] for r in a.dns)
    assert {r["content"] for r in a.dns} == {f"{a.tunnels[0]['id']}.cfargotunnel.com"}
    assert [i["type"] for i in a.idps] == ["onetimepin"]
    assert [r["email"]["email"] for r in a.groups[0]["include"]] == ["leon@example.com", "pei@example.com"]
    assert a.apps[0]["domain"] == provision.DOMAIN and len(a.apps[0]["policies"]) == 2
    assert a.apps[1]["domain"] == provision.PREVIEW_DOMAIN and a.apps[1]["policies"] == a.apps[0]["policies"]
    # only the version path is open to everyone, on each site
    assert [x["domain"] for x in a.apps[2:]] == [f"{provision.DOMAIN}/api/version", f"{provision.PREVIEW_DOMAIN}/api/version"]
    bypass = [p for p in a.policies if p["decision"] == "bypass"]
    assert len(bypass) == 1 and bypass[0]["include"] == [{"everyone": {}}]
    assert all(x["policies"] == [{"id": bypass[0]["id"], "precedence": 1}] for x in a.apps[2:])
    assert a.buckets == [provision.BUCKET] and a.registry and len(a.volumes) == 1
    assert a.firewalls[0]["inbound_rules"] == []
    assert len(a.droplets) == 1
    files = user_data(a)
    env = files["/etc/lacuna/lacuna.env"]
    assert "LACUNA_CLOUD=1" in env and "CF_ACCESS_AUD=aud-xyz" in env and "ANTHROPIC_API_KEY=sk-ant-secret" in env
    assert "CF_ACCESS_TEAM_DOMAIN=lacunastudio.cloudflareaccess.com" in env
    assert "LACUNA_OWNER_EMAIL=leon@example.com" in env
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
    assert {r["name"] for r in a.dns} == {provision.DOMAIN, provision.PREVIEW_DOMAIN}
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
    assert files["/etc/lacuna/preview-image"].strip().endswith("/lacuna:preview")
    assert "/etc/systemd/system/lacuna-update-preview.timer" in files
    unit = files["/etc/systemd/system/lacuna-update-preview.service"]
    assert "LACUNA_DATA=/data/preview" in unit and "LACUNA_SEED_FROM=/data/workspace" in unit
    assert "--exclude /data/preview" in files["/usr/local/bin/lacuna-backup"]


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
    assert len(a.tokens) == 2 and not old_tokens & {t["id"] for t in a.tokens}


def test_missing_secret_is_named(api, monkeypatch):
    a, run = api
    monkeypatch.delenv("BACKUP_PASSWORD")
    with pytest.raises(provision.ProvisionError, match="BACKUP_PASSWORD"):
        run("apply")


def test_ci_wait_live_reads_the_public_version_without_a_token(monkeypatch):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "deploy"))
    import ci
    sys.path.pop(0)
    monkeypatch.setenv("CLOUDFLARE_API_TOKEN", "t")
    tokens = [{"id": "old1", "name": "lacuna-deploy-check-1"}, {"id": "keep", "name": "someone-else"}]

    def cfh(method, path, body=None):
        p = path.split("?")[0]
        if p == "/zones":
            return 200, {"success": True, "result": [{"id": "z", "account": {"id": "acc"}}]}
        if p.endswith("/service_tokens") and method == "GET":
            return 200, {"success": True, "result": list(tokens)}
        if "/service_tokens/" in p and method == "DELETE":
            tokens[:] = [t for t in tokens if t["id"] != p.rsplit("/", 1)[1]]
            return 200, {"success": True, "result": {}}
        raise AssertionError(f"{method} {path}")       # never creates a token

    monkeypatch.setattr(ci, "cf", lambda: provision.Cloudflare(FakeHttp(cfh)))
    monkeypatch.setattr(ci.time, "sleep", lambda s: None)
    answers = iter([(302, {}), (200, {"version": "old"}), (200, {"version": "abc"})])
    seen = []
    monkeypatch.setattr(ci, "_get", lambda url, h: (seen.append((url, h)), next(answers))[1])
    ci.wait_live("abc")
    assert seen[-1] == (f"https://{provision.DOMAIN}/api/version", {})
    assert tokens == [{"id": "keep", "name": "someone-else"}]           # the old check's leftovers deleted
    answers = iter([(200, {"version": "abc"})])
    assert ci.main(["wait-live", "abc", "preview"]) == 0 and seen[-1][0] == f"https://{provision.PREVIEW_DOMAIN}/api/version"

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
