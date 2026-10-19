"""deploy/host/lacuna-update (the server's pull-based deploy) against a fake `docker`: deploys a new
image, waits while jobs run, rolls back an image that doesn't start and never retries it; the staging
copy (lacuna-update-preview.service) starts each new version on a fresh copy of the real workspace."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "deploy" / "host" / "lacuna-update"

pytestmark = pytest.mark.skipif(sys.platform == "win32" or not shutil.which("jq") or not shutil.which("flock")
                                or not shutil.which("rsync"),
                                reason="host scripts run on Linux (needs bash, jq, flock, rsync)")

FAKE_DOCKER = r'''#!/usr/bin/env python3
import json, os, sys
f = os.environ["FAKE_DOCKER_STATE"]
s = json.load(open(f))
a = sys.argv[1:]
def save(): json.dump(s, open(f, "w"))
c = s.get("container")
if a[0] in ("pull", "tag"):
    sys.exit(0)
if a[:2] == ["image", "inspect"]:
    print(s["tags"][a[-1]]); sys.exit(0)
if a[:2] == ["image", "prune"]:
    sys.exit(0)
if a[0] == "inspect":
    if not c: sys.exit(1)
    print(c["image"] if "Image" in a[2] else ("true" if c["running"] else "false")); sys.exit(0)
if a[0] == "rm":
    s["container"] = None; save(); sys.exit(0)
if a[0] == "run":
    img = a[-1]; s["container"] = {"image": img, "running": img not in s["crash"]}; s["started"].append(img)
    s["runs"].append({"name": a[a.index("--name") + 1], "mount": a[a.index("-v") + 1],
                      "env_file": a[a.index("--env-file") + 1], "memory": a[a.index("--memory") + 1]}); save()
    sys.exit(0)
if a[0] == "logs":
    print("boom"); sys.exit(0)
if a[0] == "exec":
    if not c or not c["running"] or c["image"] in s["unhealthy"]: sys.exit(1)
    if a[2] == "cat": print("v-" + c["image"]); sys.exit(0)
    code = a[-1]
    if "/api/app" in code: print(s["busy"]); sys.exit(0)
    sys.exit(0)
sys.exit(2)
'''


@pytest.fixture
def host(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    docker = bindir / "docker"
    docker.write_text(FAKE_DOCKER)
    docker.chmod(0o755)
    (tmp_path / "image").write_text("reg/lacuna:main\n")
    state = tmp_path / "docker.json"

    def set_state(**kw):
        s = json.loads(state.read_text()) if state.exists() else {
            "tags": {}, "container": None, "crash": [], "unhealthy": [], "busy": 0, "started": [], "runs": []}
        s.update(kw)
        state.write_text(json.dumps(s))

    def run(**extra):
        env = os.environ | {"PATH": f"{bindir}:{os.environ['PATH']}", "FAKE_DOCKER_STATE": str(state),
                            "LACUNA_STATE_DIR": str(tmp_path / "state"), "LACUNA_IMAGE_FILE": str(tmp_path / "image"),
                            "HEALTH_WAIT": "3", "HEALTH_POLL": "0"} | extra
        p = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
        s = json.loads(state.read_text())
        st = tmp_path / "state" / "deploy.json"
        return p.returncode, s, json.loads(st.read_text()) if st.exists() else None

    set_state()
    return set_state, run


def test_first_deploy_then_nothing_to_do(host):
    set_state, run = host
    set_state(tags={"reg/lacuna:main": "img1"})
    code, s, st = run()
    assert code == 0 and s["container"] == {"image": "img1", "running": True}
    assert st["state"] == "deployed" and st["message"] == "v-img1"
    code, s, _ = run()
    assert s["started"] == ["img1"]        # same image: left alone


def test_waits_while_a_job_runs(host):
    set_state, run = host
    set_state(tags={"reg/lacuna:main": "img1"})
    run()
    set_state(tags={"reg/lacuna:main": "img2"}, busy=1)
    code, s, st = run()
    assert s["container"]["image"] == "img1" and st["state"] == "waiting"
    set_state(busy=0)
    code, s, st = run()
    assert s["container"]["image"] == "img2" and st["state"] == "deployed"


@pytest.mark.parametrize("failure", ["crash", "unhealthy"])
def test_bad_image_rolls_back_and_is_not_retried(host, failure):
    set_state, run = host
    set_state(tags={"reg/lacuna:main": "img1"})
    run()
    set_state(tags={"reg/lacuna:main": "img2"}, **{failure: ["img2"]})
    code, s, st = run()
    assert code == 1 and s["container"] == {"image": "img1", "running": True}
    assert st["state"] == "rolled-back"
    code, s, _ = run()
    assert s["started"] == ["img1", "img2", "img1"]        # img2 not tried again
    set_state(tags={"reg/lacuna:main": "img3"})            # a newer image is tried
    code, s, st = run()
    assert s["container"]["image"] == "img3" and st["state"] == "deployed"


def test_staging_starts_each_new_version_on_a_fresh_copy(host, tmp_path):
    set_state, run = host
    real, data = tmp_path / "real", tmp_path / "preview"
    (real / "episodes" / "EP1").mkdir(parents=True)
    (real / "episodes" / "EP1" / "state.json").write_text("real")
    (real / "tmp").mkdir()
    (real / "tmp" / "upload.part").write_text("scratch")
    staging = {"LACUNA_NAME": "lacuna-preview", "LACUNA_DATA": str(data), "LACUNA_SEED_FROM": str(real),
               "LACUNA_ENV_FILE": "/etc/lacuna/preview.env", "LACUNA_OWNER": f"{os.getuid()}:{os.getgid()}",
               "LACUNA_LIMITS": "--memory 3g --cpus 2"}
    set_state(tags={"reg/lacuna:main": "img1"})
    code, s, st = run(**staging)
    assert code == 0 and st["state"] == "deployed"
    assert s["runs"][-1] == {"name": "lacuna-preview", "mount": f"{data}:/data",
                             "env_file": "/etc/lacuna/preview.env", "memory": "3g"}
    ws = data / "workspace"
    assert (ws / "episodes" / "EP1" / "state.json").read_text() == "real"
    assert not (ws / "tmp").exists() and (data / "home").is_dir() and (data / "tmp").is_dir()
    # trying things out on staging changes only the copy
    (ws / "episodes" / "EP1" / "state.json").write_text("edited on staging")
    (ws / "episodes" / "EP2").mkdir()
    run(**staging)                                           # same version: copy left as it is
    assert (ws / "episodes" / "EP1" / "state.json").read_text() == "edited on staging"
    assert (real / "episodes" / "EP1" / "state.json").read_text() == "real"
    set_state(tags={"reg/lacuna:main": "img2"})
    code, s, st = run(**staging)                             # a new version: fresh copy of the real one
    assert st["state"] == "deployed" and s["container"]["image"] == "img2"
    assert (ws / "episodes" / "EP1" / "state.json").read_text() == "real" and not (ws / "episodes" / "EP2").exists()


def test_staging_without_disk_room_keeps_the_old_version(host, tmp_path):
    set_state, run = host
    real = tmp_path / "real"
    real.mkdir()
    (real / "a").write_text("x")
    staging = {"LACUNA_NAME": "lacuna-preview", "LACUNA_DATA": str(tmp_path / "preview"), "LACUNA_SEED_FROM": str(real),
               "LACUNA_OWNER": f"{os.getuid()}:{os.getgid()}"}
    set_state(tags={"reg/lacuna:main": "img1"})
    run(**staging)
    set_state(tags={"reg/lacuna:main": "img2"})
    code, s, st = run(**staging, LACUNA_SEED_MARGIN=str(10 ** 18))
    assert code == 0 and st["state"] == "no-space" and s["container"] == {"image": "img1", "running": True}


def test_the_real_site_is_never_seeded(host, tmp_path):
    set_state, run = host
    set_state(tags={"reg/lacuna:main": "img1"})
    code, s, _ = run()
    assert s["runs"][-1] == {"name": "lacuna", "mount": "/data:/data", "env_file": "/etc/lacuna/lacuna.env",
                             "memory": "7g"}


def test_provision_cloud_init_carries_host_scripts_and_secret_files():
    sys.path.insert(0, str(REPO / "deploy"))
    try:
        import provision
    finally:
        sys.path.pop(0)
    doc = provision.cloud_init({"/etc/lacuna/lacuna.env": ("A=1\n", "0600")})
    assert doc.startswith("#cloud-config\n")
    cfg = json.loads(doc.split("\n", 1)[1])
    paths = {f["path"]: f for f in cfg["write_files"]}
    assert paths["/etc/lacuna/lacuna.env"]["permissions"] == "0600"
    for name in ("lacuna-bootstrap", "lacuna-update", "lacuna-backup"):
        assert paths[f"/usr/local/bin/{name}"]["permissions"] == "0755"
    assert "/etc/systemd/system/lacuna-update.timer" in paths
    assert cfg["runcmd"] == [["/usr/local/bin/lacuna-bootstrap"]]
