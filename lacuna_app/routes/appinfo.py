"""App version, in-app update and settings (phase 7, D51): /api/app*."""
from __future__ import annotations

from .. import appinfo
from ..asr import models_present
from ..editor import find_api_key, sdk_installed
from ..exporter import Exporter
from ..importer import Importer
from .publish import publisher_of
from ..i18n import tr


def register(app, ctx) -> None:
    ws = ctx.ws
    importer = ctx.provide("importer", lambda: Importer(ws))
    exporter = ctx.provide("exporter", lambda: Exporter(ws))
    publisher = publisher_of(ctx)

    def busy() -> list[str]:
        """Work an update restart would cut off."""
        out = []
        if importer._running:
            out.append(tr("导入（{_running}）", _running=importer._running))
        if exporter._running:
            out.append(tr("导出（{_running}）", _running=exporter._running))
        if any(j.get("state") == "running" for j in list(publisher.jobs.values())):
            out.append(tr("生成发布资料"))
        return out

    def key_status() -> dict:
        key, where = find_api_key()
        return {"present": bool(key), "source": where if key else None, "editor": ctx.adapter.name,
                "sdk": sdk_installed()}

    app.state.restart = ctx.option("restart") or (lambda code: None)
    appinfo.register(app, ctx.option("updater") or appinfo.Updater(), ws.root, busy, key_status,
                     lambda: models_present(ws.root / "models"))
