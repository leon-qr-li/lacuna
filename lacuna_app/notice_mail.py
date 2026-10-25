"""Short notice emails in the invite email's look (design A 「夜航信笺」, lacuna_app/invite_mail.py): a sign-in
from a new device (decision 2026-10-21-app-sign-in) and a new 申请试用 for the site owner.

``render`` builds {"subject", "text", "html", "inline"} in the current ``tr`` language from a title, a lead
line, a few label / value rows, one button and a closing note. Like the invite, the dark header band and the
button are pictures when they can be drawn (Gmail's dark mode on phones recolours their white text).
"""
from __future__ import annotations

import html
import re

from .i18n import tr
from .invite_mail import (BUTTON_CID, HEAD_CID, LOGO_CID, SANS, SERIF, button_png, header_png, inline_logo,
                          logo_png, unique_marks)

# browser and system from a User-Agent, for "Chrome · macOS" (no version numbers, nothing identifying)
BROWSERS = (("Edg/", "Edge"), ("OPR/", "Opera"), ("Firefox/", "Firefox"), ("Chrome/", "Chrome"), ("Safari/", "Safari"))
SYSTEMS = (("iPhone", "iOS"), ("iPad", "iPadOS"), ("Android", "Android"), ("Windows", "Windows"),
           ("Mac OS X", "macOS"), ("CrOS", "ChromeOS"), ("Linux", "Linux"))


def device_label(agent: str) -> str:
    agent = agent or ""
    browser = next((name for key, name in BROWSERS if key in agent), "")
    system = next((name for key, name in SYSTEMS if key in agent), "")
    return " · ".join(x for x in (browser, system) if x) or tr("未知设备")


def country_name(code: str | None) -> str | None:
    """Cloudflare's two-letter country (CF-IPCountry) as a name in the reader's language; None when unknown."""
    code = (code or "").strip().upper()
    if not re.fullmatch(r"[A-Z]{2}", code) or code in ("XX", "T1"):
        return None
    names = {"US": tr("美国"), "CN": tr("中国"), "CA": tr("加拿大"), "GB": tr("英国"), "JP": tr("日本"),
             "HK": tr("中国香港"), "TW": tr("中国台湾"), "SG": tr("新加坡"), "AU": tr("澳大利亚"), "DE": tr("德国"),
             "FR": tr("法国")}
    return names.get(code, code)


def render(subject: str, lead: str, rows: list[tuple[str, str]], button: str | None, link: str | None, note: str,
           kicker: str = "", steps: list[tuple[str, str]] | None = None, done: int = 0) -> dict:
    """``steps``: (title, line) pairs shown as a numbered path under the lead, the first ``done`` ticked off.
    Without a button the note moves to the small print at the bottom."""
    colon = tr("：")
    steps = steps or []
    text = "\n\n".join(x for x in [
        subject, lead, "\n".join(f"{i}. {a} · {b}" for i, (a, b) in enumerate(steps, 1)),
        "\n".join(f"{k}{colon}{v}" for k, v in rows), f"{button}\n{link}" if button else "", note,
        "Mind the gaps. Keep the voice.\nLACUNA Studio · lacunastudio.app"] if x)
    e = html.escape
    steps_html = "".join(
        f'<tr><td style="padding:8px 14px 8px 0;vertical-align:top;width:24px"><div style="width:24px;height:24px;border-radius:12px;'
        f'background:{"#0a734d" if i <= done else "#fff1ea"};color:{"#ffffff" if i <= done else "#c2410c"};'
        f'font:700 12px/24px {SANS};text-align:center">{"&#10003;" if i <= done else i}</div></td>'
        f'<td style="padding:8px 0;vertical-align:top"><div style="font:600 15px/1.5 {SANS};color:#14162e">{e(a)}</div>'
        f'<div style="font:14px/1.6 {SANS};color:#6b6e88">{e(b)}</div></td></tr>'
        for i, (a, b) in enumerate(steps, 1))
    steps_html = (f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 20px">{steps_html}</table>'
                  if steps else "")
    row_html = "".join(
        f'<tr><td style="padding:10px 0;border-top:1px solid #ececf3;font:14px {SANS};color:#8a8da6;width:120px">{e(k)}</td>'
        f'<td style="padding:10px 0;border-top:1px solid #ececf3;font:600 14px {SANS};color:#14162e;word-break:break-all">{e(v)}</td></tr>'
        for k, v in rows)
    head = header_png(subject, kicker or tr("通知 · NOTICE"))
    btn = button_png(button) if button else None
    inline = ([{"filename": "header.png", "content": head, "content_id": HEAD_CID}] if head else []) + \
        ([{"filename": "button.png", "content": btn[0], "content_id": BUTTON_CID}] if btn else [])
    logo = (f'<td><img src="cid:{LOGO_CID}" width="32" height="32" alt="LACUNA" style="display:block;border-radius:8px"></td>'
            if logo_png() else "")
    header = (f'<tr><td style="padding:0;background:#0b0e26;line-height:0"><img src="cid:{HEAD_CID}" width="560" alt="{e(subject)}" '
              f'style="display:block;width:100%;height:auto;border:0"></td></tr>') if head else f"""<tr><td class="pad" style="background:#0b0e26;background-image:radial-gradient(120% 140% at 85% 0%,#2a1f5c 0%,#0b0e26 55%);padding:24px 40px">
 <table role="presentation" cellpadding="0" cellspacing="0"><tr>{logo}
 <td style="padding-left:{10 if logo else 0}px;font:700 13px {SANS};letter-spacing:3px;color:#ffffff">LACUNA <span style="font-weight:400;color:#9aa0c8">STUDIO</span></td></tr></table>
</td></tr>"""
    body_note = f'<p style="margin:20px 0 0;font:14px/1.7 {SANS};color:#3a3d55">{e(note)}</p>' if button else ""
    foot_note = "" if button else f'<div style="margin-top:10px;font:12px/1.6 {SANS};color:#a0a3b8">{e(note)}</div>'
    title = "" if head else f'<div style="font:700 22px/1.4 {SANS};color:#14162e">{e(subject)}</div>'
    button_html = "" if not button else (f'<p style="margin:24px 0 8px"><a href="{e(link, quote=True)}"><img src="cid:{BUTTON_CID}" width="{btn[1]}" height="52" '
                   f'alt="{e(button)}" style="display:block;border:0"></a></p>') if btn else f"""<table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 8px"><tr><td style="border-radius:999px;background:#df4a22;background-image:linear-gradient(90deg,#df4a22,#d93366 55%,#8f45f0)">
  <a href="{e(link, quote=True)}" style="display:inline-block;padding:12px 30px;font:600 15px {SANS};color:#ffffff;text-decoration:none">{e(button)}</a></td></tr></table>"""
    body = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light only"><title>{e(subject)}</title><style>body{{margin:0}} @media (max-width:620px){{.wrap{{width:100%!important}} .pad{{padding-left:24px!important;padding-right:24px!important}}}}</style></head>
<body class="body" style="margin:0;padding:0;background:#f1f1f6"><div style="display:none;max-height:0;overflow:hidden">{e(lead)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f1f6"><tr><td align="center" style="padding:40px 12px">
<table class="wrap" role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:560px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 40px rgba(9,11,31,.12)">
{header}
<tr><td class="pad" style="padding:32px 40px 8px">
 {title}
 <p style="margin:12px 0 20px;font:15px/1.7 {SANS};color:#3a3d55">{e(lead)}</p>
 {steps_html}
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-bottom:1px solid #ececf3">{row_html}</table>
 {body_note}
 {button_html}
</td></tr>
<tr><td class="pad" style="padding:24px 40px 30px">
 <div style="border-top:1px solid #ececf3;padding-top:18px;font:italic 13px {SERIF};color:#5a5d78">Mind the gaps. Keep the voice.</div>
 {foot_note}<div style="margin-top:8px;font:12px {SANS};color:#a0a3b8">LACUNA Studio · lacunastudio.app</div>
</td></tr></table>
</td></tr></table></body></html>"""
    return {"subject": subject, "text": text, "html": unique_marks(body), "inline": inline + ([] if head else inline_logo())}


def new_device(email: str, device: str, when: str, where: str | None, link: str) -> dict:
    rows = [(tr("时间"), when), (tr("设备"), device)] + ([(tr("大致位置"), where)] if where else [])
    return render(tr("新设备登录了你的 LACUNA 账号"),
                  tr("有人刚刚在一台新设备上登录了 {email}。", email=email), rows,
                  tr("检查登录设备"), link,
                  tr("是你本人就不用管。不是你的话，马上改密码，并在 设置 → 账号与安全 里退出这台设备。"),
                  tr("安全提醒 · SECURITY"))


TRACKS = {"separate": lambda: tr("每位主持人一条分轨"), "mixed": lambda: tr("所有人混在一条录音里"),
          "unsure": lambda: tr("不确定")}


def access_request(email: str, show: str, note: str, link: str, tracks: str | None = None) -> dict:
    rows = [(tr("邮箱"), email), (tr("节目"), show or "—")] + ([(tr("想用 LACUNA 做什么"), note)] if note else []) + \
        ([(tr("录音"), TRACKS[tracks]())] if tracks in TRACKS else [])
    return render(tr("新的试用申请：{email}", email=email),
                  tr("有人在登录页申请试用 LACUNA。"), rows, tr("去发邀请"), link,
                  tr("在 设置 → 成员与邀请 → 试用申请 里一键发邀请或忽略。"), tr("试用申请 · REQUEST"))


def request_received(email: str, show: str, when: str) -> dict:
    """To the person who asked on the sign-in page (Leon 2026-10-21, design A 「夜航信笺」): it arrived, and
    what happens next. No link: the invite, if it comes, is its own mail."""
    rows = [(tr("申请邮箱"), email)] + ([(tr("节目"), show)] if show else []) + [(tr("提交时间"), when)]
    steps = [(tr("申请已提交"), tr("我们已收到你的信息")),
             (tr("审核通过后发送邀请"), tr("邀请邮件会发到这个邮箱，链接 7 天内有效")),
             (tr("设置密码，开始使用"), tr("按邀请邮件的步骤设置密码和两步验证"))]
    return render(tr("我们收到了你的 LACUNA 试用申请"),
                  tr("感谢你关注 LACUNA Studio。你的申请已经登记，我们会尽快完成审核。接下来会这样进行："),
                  rows, None, None, tr("如果这不是你本人提交的申请，忽略这封邮件即可，不会创建任何账号。"),
                  tr("申请已收到 · RECEIVED"), steps, done=1)


def collab_request(email: str, show: str, by: str, link: str) -> dict:
    """To the site owner: a show admin wants to bring in someone without an account (新成员需站长批准)."""
    rows = [(tr("邮箱"), email), (tr("节目"), show or "—"), (tr("谁邀请的"), by)]
    return render(tr("新的搭档申请：{email}", email=email),
                  tr("{by} 想邀请 {email} 一起做「{show}」。对方还没有 LACUNA 账号，需要你批准。", by=by, email=email, show=show),
                  rows, tr("去处理"), link,
                  tr("在 设置 → 成员与邀请 → 试用申请 里批准（自动发邀请）或忽略。"), tr("搭档申请 · REQUEST"))


def collab_declined(email: str, show: str) -> dict:
    """To the show admin whose 搭档申请 the owner dismissed."""
    return render(tr("搭档申请没有通过：{email}", email=email),
                  tr("你邀请 {email} 加入「{show}」的申请这次没有通过，没有发出邀请。", email=email, show=show),
                  [(tr("邮箱"), email), (tr("节目"), show or "—")], None, None,
                  tr("对方以后也可以自己在 LACUNA 登录页申请试用。"), tr("搭档申请 · REQUEST"))


def raw_tracks_reminder(show: str, episodes: list[dict], origin: str | None) -> dict:
    """To a show's creator, 30 days before raw tracks are deleted (retention.py, decision 2026-10-25-audio-retention).
    `episodes`: {"title", "on" (epoch seconds)}."""
    import time as _time
    rows = [(e["title"], tr("{date} 删除", date=_time.strftime("%Y-%m-%d", _time.gmtime(e["on"])))) for e in episodes[:20]]
    if len(episodes) > 20:
        rows.append((tr("还有"), tr("{n} 集", n=len(episodes) - 20)))
    return render(tr("「{show}」有 {n} 集的原始音轨 30 天后删除", show=show or "LACUNA", n=len(episodes)),
                  tr("这些剧集已经将近 12 个月没有打开过了。到期后只删除原始分轨；逐字稿、剪辑记录、节目介绍和最新的导出成品都会一直保留。"),
                  rows, tr("打开 LACUNA") if origin else None, origin,
                  tr("想继续保留哪一集，打开它一次就行，保留期会从那天重新算 12 个月。"), tr("保留提醒 · NOTICE"))
