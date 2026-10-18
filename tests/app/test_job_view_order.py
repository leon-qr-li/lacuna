"""The poster and publish pages poll `view()` until the job is no longer running. `view()` must read
the job before the document: if the job finishes between the two reads, the page then sees
"running" once more and polls again, instead of "done" next to the document from before the job
(no cover / no pack until a reload; seen as a flaky CI test under load)."""
from pathlib import Path


from lacuna_app import create_app
from lacuna_app.editor import MockEditorAdapter
from lacuna_app.poster import ClaudeDesigner, Posters
from lacuna_app.publish import ClaudePublisher, Publisher
from lacuna_app.store import Workspace

from .fake_claude import FakePosterAnthropic, FakePublishAnthropic
from .synth import EPISODE, make_workspace


def finishes_during_load(svc, ep, result):
    """Make svc.load return the document as it was, while the job finishes right after that read."""
    real = svc.load

    def load(e):
        svc.load = real                  # once: the job itself reads and writes normally
        before = real(e)
        with svc._lock:
            svc.jobs.pop(ep.id, None)
        result()
        with svc._lock:
            svc.jobs[ep.id].update(state="done", finished=1.0)
        return before
    svc.load = load
    with svc._lock:
        svc.jobs[ep.id] = {"kind": "x", "state": "running", "stage": "", "started": 0.0, "finished": None,
                           "error": None}


def test_view_never_reports_done_with_the_old_document(tmp_path):
    ws = Workspace(make_workspace(tmp_path / "ws"))
    pub = Publisher(ws, lambda: ClaudePublisher(client=FakePublishAnthropic()))
    posters = Posters(ws, pub, lambda: ClaudeDesigner(client=FakePosterAnthropic()))
    app = create_app(ws.root, MockEditorAdapter(), web_dist=Path("/nonexistent"), publisher=pub, posters=posters)
    ep = app.state.ctx.get(EPISODE)
    pub.start(ep, wait=True)
    posters.generate(ep, wait=True)

    finishes_during_load(posters, ep, lambda: posters.choose(ep, "v1", wait=True))
    v = posters.view(ep)
    assert not (v["job"]["state"] == "done" and v["cover"] is None)
    assert posters.view(ep)["cover"] is not None

    old = pub.load(ep)
    finishes_during_load(pub, ep, lambda: pub.start(ep, wait=True))
    v = pub.view(ep)
    assert v["job"]["state"] == "running" or v["pack"] is not None
    assert old is not None
