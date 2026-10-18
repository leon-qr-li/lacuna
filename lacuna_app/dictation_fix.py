"""Voice input, second pass: fix homophones and names in the local recognition using context.

SenseVoice hears one clip at a time with no idea what the show is about, so "Pei" comes out as 陪,
为什么 as 胃什么, 游戏 as 油戏. After the local pass, one small request to a fast, cheap model
(Haiku, ~$0.0003 per clip) gets the recognised text plus what it needs to pick the right
characters: the hosts' names, names Leon corrected before (names.json), the episode title and the
films/terms of its publish pack, the transcript around the playhead and the last chat turns.
It may only swap mis-heard words; meaning, wording and tone stay. Only text goes out (never
audio). Any failure, timeout or an answer that rewrites too much falls back to the local text,
so dictation never gets worse or blocks. Off with ``LACUNA_DICTATION_FIX=off``.
"""
from __future__ import annotations

import difflib
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .editor import find_api_key, sdk_installed
from .i18n import AI_NAME_RULE

HOSTS = ("Leon", "Pei")
TIMEOUT_S = 8.0
MIN_SIMILARITY = 0.5      # below this the "fix" rewrote the sentence: keep what was heard

SYSTEM = (Path(__file__).resolve().parent / "prompts" / "dictation_fix.txt").read_text(encoding="utf-8").strip() + AI_NAME_RULE

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {"text": {"type": "string", "description": "the corrected text"}},
}


@dataclass
class FixContext:
    names: list[str] = field(default_factory=lambda: list(HOSTS))
    corrections: list[dict] = field(default_factory=list)   # names.json: {"wrong", "right"}
    episode_title: str = ""
    terms: list[str] = field(default_factory=list)          # films, glossary of the episode
    transcript: str = ""                                    # around the playhead
    chat: list[str] = field(default_factory=list)           # what Leon said recently
    where: str = "chat"                                     # chat | poster

    def as_json(self, raw: str) -> str:
        doc: dict[str, Any] = {"dictated_text": raw, "typed_into": {
            "chat": "the AI producer chat of the editing page (editing instructions)",
            "poster": "a one-line change request for an episode cover image"}.get(self.where, self.where),
            "people": self.names}
        if self.corrections:
            doc["names_corrected_before"] = [f"{c['wrong']} → {c['right']}" for c in self.corrections]
        if self.episode_title:
            doc["episode_title"] = self.episode_title
        if self.terms:
            doc["episode_terms"] = self.terms
        if self.transcript:
            doc["episode_transcript_near_playhead"] = self.transcript
        if self.chat:
            doc["leon_said_earlier"] = self.chat
        return json.dumps(doc, ensure_ascii=False)


def enabled_by_env() -> bool:
    return os.environ.get("LACUNA_DICTATION_FIX", "on").strip().lower() not in ("0", "off", "false", "no")


def similar_enough(raw: str, fixed: str) -> bool:
    if not fixed.strip():
        return False
    if len(raw) <= 4:
        return len(fixed) <= 12
    return difflib.SequenceMatcher(None, raw, fixed).ratio() >= MIN_SIMILARITY


class DictationFixer:
    """`client` can be injected (tests use a fake with ``messages.create``)."""

    model = "claude-haiku-5-5"

    def __init__(self, api_key: str | None = None, client: Any = None):
        if api_key is None and client is None:
            api_key, _ = find_api_key()
        self.api_key = api_key
        self._client = client

    @property
    def available(self) -> bool:
        return enabled_by_env() and (self._client is not None or (bool(self.api_key) and sdk_installed()))

    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(api_key=self.api_key, timeout=TIMEOUT_S, max_retries=0)
        return self._client

    def request(self, raw: str, ctx: FixContext) -> dict:
        return dict(model=self.model, max_tokens=1000, system=SYSTEM,
                    output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                    messages=[{"role": "user", "content": ctx.as_json(raw)}])

    def fix(self, raw: str, ctx: FixContext) -> dict:
        """{"text", "corrected", "seconds"[, "error"]}: the local text whenever anything goes wrong."""
        out = {"text": raw, "corrected": False, "seconds": 0.0}
        if not raw.strip() or not self.available:
            return out
        t0 = time.monotonic()
        try:
            resp = self.client.messages.create(**self.request(raw, ctx))
            text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
            fixed = str(json.loads(text)["text"]).strip() if resp.stop_reason != "refusal" else ""
        except Exception as e:      # noqa: BLE001 - dictation must never fail because of this pass
            return out | {"seconds": round(time.monotonic() - t0, 2), "error": type(e).__name__}
        out["seconds"] = round(time.monotonic() - t0, 2)
        if similar_enough(raw, fixed):
            out |= {"text": fixed, "corrected": fixed != raw}
        return out
