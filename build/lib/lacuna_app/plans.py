"""Plans (decision 2026-10-21-plans): 免费体验 / 基础版 / 专业版. Every feature is in every plan; they differ
only in how much: audio hours, shows, collaborators per show. A plan belongs to an account, and a show
uses the allowance of the account that made it (its collaborators don't spend their own).

Audio hours are counted and enforced in batch 5 (decision ai-included-hour-quota); shows and
collaborators are enforced now. Hosts are at most 4 on every plan (decision four-hosts-max).
Nobody pays yet: the site owner or a site admin sets the plan in 设置 → 成员与邀请.
"""
from __future__ import annotations

from .i18n import N_, tr

TRIAL, BASIC, PRO = "trial", "basic", "pro"
DEFAULT = BASIC                      # a new invitee
ORDER = (TRIAL, BASIC, PRO)

# hours: per month, except the trial's one-time hour; None = unlimited
PLANS: dict[str, dict] = {
    TRIAL: {"name": N_("免费体验"), "hours": 1, "hours_once": True, "shows": 1, "collaborators": 0},
    BASIC: {"name": N_("基础版"), "hours": 4, "hours_once": False, "shows": 1, "collaborators": 2},
    PRO: {"name": N_("专业版"), "hours": 12, "hours_once": False, "shows": 5, "collaborators": None},
}
HOSTS = 4


class PlanLimit(Exception):
    """A plan's limit was reached; the message says which and what to do."""


def check(plan: str) -> str:
    if plan not in PLANS:
        raise ValueError(f"unknown plan {plan!r}")
    return plan


def limits(plan: str | None) -> dict:
    return PLANS.get(plan or DEFAULT, PLANS[DEFAULT])


def public() -> list[dict]:
    """The plans as the interface shows them (names in the reader's language)."""
    return [{"id": p, **PLANS[p], "name": tr(PLANS[p]["name"]), "hosts": HOSTS} for p in ORDER]


def check_shows(plan: str | None, owned: int) -> None:
    """Before someone creates a show: `owned` = shows they made that still exist (archived ones count)."""
    lim = limits(plan)["shows"]
    if lim is not None and owned >= lim:
        raise PlanLimit(tr("你的套餐「{plan}」最多 {n} 个节目。想要更多，请联系我们换套餐。",
                           plan=tr(limits(plan)["name"]), n=lim))


def check_collaborators(plan: str | None, others: int) -> None:
    """Before someone joins a show: `others` = people in it besides the person who made it."""
    lim = limits(plan)["collaborators"]
    if lim is not None and others >= lim:
        if lim == 0:
            raise PlanLimit(tr("「{plan}」不能邀请协作者。想和别人一起做节目，请联系我们换套餐。", plan=tr(limits(plan)["name"])))
        raise PlanLimit(tr("这个节目的套餐「{plan}」最多 {n} 位协作者。想要更多，请联系我们换套餐。",
                           plan=tr(limits(plan)["name"]), n=lim))
