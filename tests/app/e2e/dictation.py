"""Voice input (D43): real upload + ffmpeg decode, a fake recogniser that "hears" one fixed sentence."""
from pathlib import Path


def configure(mode: str, ws: Path, svc: dict) -> None:
    if mode != "ai":
        return
    from lacuna_app.dictation import Dictation

    svc["dictation"] = Dictation(Path(ws) / "models", backend=lambda x: "这句删掉")
