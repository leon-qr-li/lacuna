"""用户反馈 (feedback batch, Leon 2026-10-24): what beta users tell us, kept on our own server for the admin.

Everything a person sends goes to the site database's own ``feedback`` table (made here, not in db.py's
schema list, so this feature stays in its own files) and screenshots to ``<root>/feedback/<id>.jpg|png``. Nothing
of it goes to the AI, the event log or the code repository. The site owner reads and answers in the admin
(its own batch); until then ``reply`` is called by the owner-only API in routes/feedback.py.

Kinds a person writes from the 反馈 panel: ``bug`` (遇到问题), ``idea`` (我有个想法), ``praise`` (夸一句).
Answers to the one-question prompts are kinds too: ``rate`` (after the first export) and ``pmf`` (after the
third episode); they never show in 我的反馈. A show's three optional questions (asked when it is made) are kept
per show in ``profiles``.

The prompts ask at most once in ``PROMPT_GAP_S`` per person, never again after 不再问我, and each one only
until it is answered.
"""
from __future__ import annotations

import base64
import re
import secrets
import time
from pathlib import Path
from typing import Callable

from . import db as sitedb
from .i18n import tr

KINDS = ("bug", "idea", "praise")
PROMPTS = ("rate", "pmf", "nps")
# 已收到 → 在处理 / 在计划中 → 已修好 / 已上线, or 暂不做 (with a reason)
STATUSES = ("received", "working", "planned", "fixed", "shipped", "declined")
PROMPT_GAP_S = 7 * 86400
PMF_AFTER = 3              # episodes exported before the 「如果明天用不了」 question
NPS_AFTER = 3              # 推荐意愿 0–10 (decision 2026-10-24-admin-site): after the 3rd export, then every 3 months
NPS_EVERY_S = 90 * 86400
MAX_TEXT = 4000
MAX_SHOT = 6 * 1024 * 1024
MAX_ACTIONS = 20
ADOPT_HOURS = 1            # 采纳送 1 小时 (counted once hour quotas exist, batch 5)

SCHEMA = """
CREATE TABLE IF NOT EXISTS feedback (id TEXT PRIMARY KEY, created REAL NOT NULL, email TEXT NOT NULL,
                                     kind TEXT NOT NULL, status TEXT NOT NULL, unread INTEGER NOT NULL DEFAULT 0,
                                     data TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS feedback_email ON feedback(email, created);
CREATE TABLE IF NOT EXISTS feedback_profiles (show_id TEXT PRIMARY KEY, email TEXT NOT NULL, created REAL NOT NULL,
                                              data TEXT NOT NULL);
"""

REGIONS = ("na", "eu", "oceania", "asia", "cn")
EDITING = ("self", "hired", "none", "new")
SAVED = ("none", "half", "1-2h", "2h+", "never")
PMF = ("very", "somewhat", "not")
IMPORTANCE = ("nice", "need", "fine")
SHOT_RX = re.compile(r"^data:image/(png|jpeg);base64,")


class FeedbackError(ValueError):
    pass


def _short(v, n: int) -> str:
    return str(v or "").strip()[:n]


def _clean_context(ctx: dict | None) -> dict:
    """What the panel attaches by itself: the page, the episode, the app and the last steps. Short strings
    only; nothing the person typed elsewhere."""
    ctx = ctx if isinstance(ctx, dict) else {}
    out = {k: _short(ctx.get(k), 300) for k in ("page", "title", "episode", "lang", "error", "error_code", "browser")
           if ctx.get(k)}
    at = ctx.get("at")
    if isinstance(at, (int, float)) and at >= 0:
        out["at"] = round(float(at), 1)
    steps = ctx.get("actions")
    if isinstance(steps, list):
        out["actions"] = [_short(s, 200) for s in steps[-MAX_ACTIONS:] if isinstance(s, str) and s.strip()]
    return out


class Feedback:
    def __init__(self, database: sitedb.DB, root: Path, clock: Callable[[], float] = time.time):
        self.db = database
        self.dir = Path(root) / "feedback"
        self.now = clock
        with self.db.tx() as c:
            c.executescript_inside(SCHEMA)

    # ---------------------------------------------------------------- writing
    def add(self, email: str, kind: str, text: str, *, source: str = "button", context: dict | None = None,
            importance: str | None = None, quote_ok: bool = False, platforms: list | None = None,
            shot: str | None = None, show: dict | None = None, version: str = "") -> dict:
        if kind not in KINDS:
            raise FeedbackError(tr("没有这种反馈"))
        context = _clean_context(context)
        text = (text or "").strip()
        if not text and source == "error":
            text = context.get("error", "")          # 「告诉我们」 from an error: the error says it all
        if not text:
            raise FeedbackError(tr("先写几句再发送"))
        if len(text) > MAX_TEXT:
            raise FeedbackError(tr("写得太长了，请控制在 {n} 字以内", n=MAX_TEXT))
        fid = "fb_" + secrets.token_hex(6)
        data = {"text": text, "source": source if source in ("button", "error", "publish") else "button",
                "context": context, "show": show or None, "version": version, "shot": False}
        if kind == "idea" and importance in IMPORTANCE:
            data["importance"] = importance
        if kind == "praise":
            data["quote_ok"] = bool(quote_ok)
        if platforms:
            data["platforms"] = [_short(p, 40) for p in platforms if isinstance(p, str)][:8]
        if shot:
            data["shot"] = self._save_shot(fid, shot)
        now = self.now()
        with self.db.tx() as c:
            c.execute("INSERT INTO feedback (id, created, email, kind, status, unread, data) VALUES (?,?,?,?,?,0,?)",
                      (fid, now, email, kind, "received", sitedb.dumps(data)))
        return self.get(fid)

    def _save_shot(self, fid: str, shot: str) -> bool:
        m = SHOT_RX.match(shot)
        if not m:
            raise FeedbackError(tr("截图格式不对"))
        try:
            raw = base64.b64decode(shot[m.end():], validate=True)
        except ValueError:
            raise FeedbackError(tr("截图格式不对")) from None
        if len(raw) > MAX_SHOT:
            raise FeedbackError(tr("截图太大了"))
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / f"{fid}.{'jpg' if m.group(1) == 'jpeg' else 'png'}").write_bytes(raw)
        return True

    def answer(self, email: str, kind: str, answer: dict, show: dict | None = None, version: str = "") -> dict:
        """A one-question prompt's answer (``rate`` / ``pmf`` / ``nps``), kept for the admin."""
        if kind not in PROMPTS:
            raise FeedbackError(tr("没有这种反馈"))
        a = answer if isinstance(answer, dict) else {}
        data: dict = {"text": _short(a.get("text"), MAX_TEXT), "show": show or None, "version": version}
        if kind == "rate":
            stars = a.get("stars")
            if not isinstance(stars, int) or not 1 <= stars <= 5:
                raise FeedbackError(tr("先选几颗星"))
            data["stars"] = stars
            if a.get("saved") in SAVED:
                data["saved"] = a["saved"]
        elif kind == "nps":
            score = a.get("score")
            if not isinstance(score, int) or isinstance(score, bool) or not 0 <= score <= 10:
                raise FeedbackError(tr("先选一个分数"))
            data["score"] = score
        else:
            if a.get("choice") not in PMF:
                raise FeedbackError(tr("先选一项"))
            data["choice"] = a["choice"]
        fid = "fb_" + secrets.token_hex(6)
        with self.db.tx() as c:
            c.execute("INSERT INTO feedback (id, created, email, kind, status, unread, data) VALUES (?,?,?,?,?,0,?)",
                      (fid, self.now(), email, kind, "received", sitedb.dumps(data)))
        return self.get(fid)

    def reply(self, fid: str, text: str | None = None, status: str | None = None,
              adopted: bool | None = None) -> dict:
        """The site owner answers (the admin later): a reply, a status, 采纳. The person sees it in 我的反馈
        with a red dot until they look."""
        row = self._row(fid)
        if row is None:
            raise FeedbackError(tr("没有这条反馈"))
        data = row["data"]
        if status is not None and status not in STATUSES:
            raise FeedbackError(tr("没有这个状态"))
        text = (text or "").strip()
        if text:
            data.setdefault("replies", []).append({"text": text[:MAX_TEXT], "at": self.now()})
        if adopted is not None and adopted != bool(data.get("adopted")):
            data["adopted"] = bool(adopted)
            data["bonus_hours"] = ADOPT_HOURS if adopted else 0
            data["adopted_at"] = self.now() if adopted else None
        new_status = status or row["status"]
        with self.db.tx() as c:
            c.execute("UPDATE feedback SET status = ?, unread = 1, data = ? WHERE id = ?",
                      (new_status, sitedb.dumps(data), fid))
        return self.get(fid)

    def seen(self, email: str) -> None:
        with self.db.tx() as c:
            c.execute("UPDATE feedback SET unread = 0 WHERE email = ? AND unread = 1", (email,))

    # ---------------------------------------------------------------- reading
    def _row(self, fid: str) -> dict | None:
        r = self.db.query("SELECT * FROM feedback WHERE id = ?", (fid,))
        if not r:
            return None
        r = r[0]
        return {"id": r["id"], "created": r["created"], "email": r["email"], "kind": r["kind"],
                "status": r["status"], "unread": bool(r["unread"]), "data": sitedb.loads(r["data"])}

    def get(self, fid: str) -> dict | None:
        r = self._row(fid)
        return r and self._view(r)

    @staticmethod
    def _view(r: dict) -> dict:
        d = r["data"]
        return {"id": r["id"], "created": r["created"], "email": r["email"], "kind": r["kind"], "status": r["status"],
                "unread": r["unread"], "text": d.get("text", ""), "source": d.get("source"), "shot": bool(d.get("shot")),
                "show": d.get("show"), "context": d.get("context") or {}, "importance": d.get("importance"),
                "quote_ok": d.get("quote_ok"), "platforms": d.get("platforms") or [], "replies": d.get("replies") or [],
                "adopted": bool(d.get("adopted")), "bonus_hours": d.get("bonus_hours") or 0,
                "stars": d.get("stars"), "saved": d.get("saved"), "choice": d.get("choice"), "score": d.get("score"),
                "version": d.get("version")}

    def mine(self, email: str) -> list[dict]:
        """What the person wrote (not their prompt answers), newest first, for 我的反馈."""
        rows = self.db.query(
            f"SELECT * FROM feedback WHERE email = ? AND kind IN ({','.join('?' * len(KINDS))}) ORDER BY created DESC",
            (email, *KINDS))
        out = []
        for r in rows:
            v = self._view({"id": r["id"], "created": r["created"], "email": r["email"], "kind": r["kind"],
                            "status": r["status"], "unread": bool(r["unread"]), "data": sitedb.loads(r["data"])})
            out.append({k: v[k] for k in ("id", "created", "kind", "status", "unread", "text", "shot", "show",
                                          "importance", "quote_ok", "replies", "adopted", "bonus_hours", "source")}
                       | {"episode": v["context"].get("episode")})
        return out

    def unread(self, email: str) -> int:
        return self.db.query("SELECT COUNT(*) AS n FROM feedback WHERE email = ? AND unread = 1", (email,))[0]["n"]

    def all(self) -> list[dict]:
        """Everything, newest first (the owner's temporary list until the admin exists)."""
        return [self._view({"id": r["id"], "created": r["created"], "email": r["email"], "kind": r["kind"],
                            "status": r["status"], "unread": bool(r["unread"]), "data": sitedb.loads(r["data"])})
                for r in self.db.query("SELECT * FROM feedback ORDER BY created DESC")]

    def shot_path(self, fid: str) -> Path | None:
        return next((p for p in (self.dir / f"{fid}.png", self.dir / f"{fid}.jpg") if p.is_file()), None)

    def forget(self, email: str) -> None:
        """An account was deleted: what it wrote goes with it (screenshots too)."""
        for r in self.db.query("SELECT id FROM feedback WHERE email = ?", (email,)):
            while (p := self.shot_path(r["id"])) is not None:
                p.unlink(missing_ok=True)
        with self.db.tx() as c:
            c.execute("DELETE FROM feedback WHERE email = ?", (email,))
            c.execute("DELETE FROM feedback_profiles WHERE email = ?", (email,))

    def clear(self) -> None:
        """E2E only: start from nothing (the shared test server keeps its site database between runs and retries)."""
        for r in self.db.query("SELECT DISTINCT email FROM feedback"):
            self.forget(r["email"])
        with self.db.tx() as c:
            c.execute("DELETE FROM feedback_profiles")
            c.execute("DELETE FROM meta WHERE key LIKE 'fbprompt:%'")

    # ---------------------------------------------------------------- a show's three questions
    def set_profile(self, email: str, show_id: str, answers: dict) -> dict:
        a = answers if isinstance(answers, dict) else {}
        data = {k: a[k] for k, ok in (("region", REGIONS), ("editing", EDITING)) if a.get(k) in ok}
        langs = a.get("lang")
        if langs in ("zh", "en", "mixed", "other"):
            data["lang"] = langs
        with self.db.tx() as c:
            c.execute("INSERT OR REPLACE INTO feedback_profiles (show_id, email, created, data) VALUES (?,?,?,?)",
                      (show_id, email, self.now(), sitedb.dumps(data)))
        return data

    def profile(self, show_id: str) -> dict | None:
        r = self.db.query("SELECT data FROM feedback_profiles WHERE show_id = ?", (show_id,))
        return sitedb.loads(r[0]["data"]) if r else None

    # ---------------------------------------------------------------- one-question prompts
    def _prompt_state(self, email: str) -> dict:
        raw = self.db.meta(f"fbprompt:{email}")
        try:
            return sitedb.loads(raw) if raw else {}
        except ValueError:
            return {}

    def _save_prompt_state(self, email: str, st: dict) -> None:
        self.db.set_meta(f"fbprompt:{email}", sitedb.dumps(st))

    def due(self, email: str, exported: int) -> str | None:
        """Which question to ask now that an export finished (``exported``: the person's own episodes with an
        export), or None."""
        st = self._prompt_state(email)
        if st.get("never") or self.now() - st.get("last", 0) < PROMPT_GAP_S:
            return None
        done = st.get("done", [])
        if exported >= PMF_AFTER and "pmf" not in done:
            return "pmf"
        if exported >= 1 and "rate" not in done:
            return "rate"
        if exported >= NPS_AFTER and self.now() - st.get("nps_at", 0) >= NPS_EVERY_S:
            return "nps"
        return None

    def reset_prompts(self, email: str) -> None:
        """Forget what the person was asked (the owner's 验收 of the prompts with a test account)."""
        self.db.set_meta(f"fbprompt:{email}", "")

    def prompt_result(self, email: str, kind: str, outcome: str) -> None:
        """``sent``: answered (not asked again); ``later``: ask another time (after the gap); ``never``."""
        if kind not in PROMPTS or outcome not in ("sent", "later", "never"):
            raise FeedbackError(tr("没有这种反馈"))
        st = self._prompt_state(email)
        st["last"] = self.now()
        if outcome == "sent":
            st["done"] = sorted(set(st.get("done", [])) | {kind})
            if kind == "nps":
                st["nps_at"] = self.now()
        elif outcome == "never":
            st["never"] = True
        self._save_prompt_state(email, st)


# ---------------------------------------------------------------- the email when the owner answers
def status_name(status: str) -> str:
    return {"received": tr("已收到"), "working": tr("在处理"), "planned": tr("在计划中"), "fixed": tr("已修好"),
            "shipped": tr("已上线"), "declined": tr("暂不做")}.get(status, status)


def reply_mail(item: dict, link: str) -> dict:
    """「你的反馈有回复了」 in the reader's language (call inside ``speaking``), in the notice mails' look."""
    from . import notice_mail
    when = time.strftime("%Y-%m-%d", time.gmtime(item["created"]))
    said = item["text"] if len(item["text"]) <= 120 else item["text"][:118] + "…"
    rows = [(tr("你的反馈"), said), (tr("提交时间"), when), (tr("状态"), status_name(item["status"]))]
    last = (item.get("replies") or [{}])[-1].get("text")
    if last:
        rows.append((tr("LACUNA 团队回复"), last))
    lead = tr("你的反馈有新的进展。谢谢你帮 LACUNA 变得更好。")
    if item.get("adopted"):
        lead += tr("你的建议被采纳了，本月多给你 {n} 小时音频额度。", n=item.get("bonus_hours") or ADOPT_HOURS)
    return notice_mail.render(tr("你的 LACUNA 反馈有回复了"), lead, rows, tr("查看我的反馈"), link,
                              tr("不用回复这封邮件。想补充什么，在 LACUNA 右上角点「反馈」。"), tr("反馈 · FEEDBACK"))
