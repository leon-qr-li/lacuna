"""App version and settings (phase 7, D51): /api/app*."""
from __future__ import annotations

from .. import appinfo, upload_parts
from ..asr import models_present
from ..editor import find_api_key, sdk_installed
from ..exporter import Exporter
from ..importer import Importer
from .publish import publisher_of
from ..i18n import tr


def register(app, ctx) -> None:
    ws = ctx.ws
    importer = ctx.provide("importer", lambda: Importer(ws, models_dir=ctx.models_dir))
    exporter = ctx.provide("exporter", lambda: Exporter(ws))
    publisher = publisher_of(ctx)

    def busy() -> list[str]:
        """Work a restart would cut off, in every show on the server, and files being uploaded: the cloud
        host's updater (deploy/host/lacuna-update) waits for it."""
        out = []
        states = [app.state] + [a.state for a in list(getattr(app.state, "space_apps", {}).values())]
        for st in states:
            imp, exp, pub = (getattr(st, n, None) for n in ("importer", "exporter", "publisher"))
            if st is app.state:
                imp, exp, pub = importer, exporter, publisher
            for eid in (imp.active() if imp is not None else []):
                out.append(tr("导入（{_running}）", _running=eid))
            if exp is not None and exp._running:
                out.append(tr("导出（{_running}）", _running=exp._running))
            if pub is not None and any(j.get("state") == "running" for j in list(pub.jobs.values())):
                out.append(tr("生成发布资料"))
        if n := upload_parts.active():
            out.append(tr("上传（{n} 个文件）", n=n))
        cold = getattr(app.state, "cold", None)
        if cold is not None and (n := cold.active()):
            out.append(tr("云存储音频搬运（{n} 集）", n=n))
        return out

    def key_status() -> dict:
        key, where = find_api_key()
        return {"present": bool(key), "source": where if key else None, "editor": ctx.adapter.name,
                "sdk": sdk_installed()}

    appinfo.register(app, ws.root, busy, key_status,
                     lambda: models_present(ctx.models_dir))
