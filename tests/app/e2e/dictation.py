"""Voice input (D43): real upload + ffmpeg decode, a fake recogniser that "hears" one fixed sentence
with a mis-heard name, and a fake context pass that only fixes it when the page sent the episode."""
import json
from pathlib import Path
from types import SimpleNamespace


class _ContextFix:
    def create(self, **kw):
        doc = json.loads(kw["messages"][0]["content"])
        text = doc["dictated_text"]
        if doc.get("episode_title") and "Pei" in doc.get("people", []):
            text = text.replace("陪", "Pei")
        return SimpleNamespace(stop_reason="end_turn",
                               content=[SimpleNamespace(type="text", text=json.dumps({"text": text}, ensure_ascii=False))])


def configure(mode: str, ws: Path, svc: dict) -> None:
    from lacuna_app.dictation_fix import DictationFixer

    if mode != "ai":
        svc["dictation_fixer"] = DictationFixer(api_key="")      # never a real request from E2E
        return
    from lacuna_app.dictation import Dictation

    svc["dictation"] = Dictation(Path(ws) / "models", backend=lambda x: "陪说这句删掉")
    svc["dictation_fixer"] = DictationFixer(client=SimpleNamespace(messages=_ContextFix()))
