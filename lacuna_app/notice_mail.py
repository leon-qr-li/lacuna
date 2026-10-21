"""Short notice emails in the invite email's look (design A 「夜航信笺」, lacuna_app/invite_mail.py): a sign-in
from a new device (decision 2026-10-21-app-sign-in) and a new 申请试用 for the site owner.

``render`` builds {"subject", "text", "html"} in the current ``tr`` language from a title, a lead line,
a few label / value rows, one button and a closing note.
"""
from __future__ import annotations

import html
import re

from .i18n import tr
from .invite_mail import LOGO_CID, SANS, SERIF, logo_png, white

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


def render(subject: str, lead: str, rows: list[tuple[str, str]], button: str, link: str, note: str) -> dict:
    colon = tr("：")
    text = "\n\n".join([subject, lead, "\n".join(f"{k}{colon}{v}" for k, v in rows), f"{button}\n{link}", note,
                        "Mind the gaps. Keep the voice.\nLACUNA Studio · lacunastudio.app"])
    e = html.escape
    row_html = "".join(
        f'<tr><td style="padding:10px 0;border-top:1px solid #ececf3;font:14px {SANS};color:#8a8da6;width:120px">{e(k)}</td>'
        f'<td style="padding:10px 0;border-top:1px solid #ececf3;font:600 14px {SANS};color:#14162e;word-break:break-all">{e(v)}</td></tr>'
        for k, v in rows)
    logo = (f'<td><img src="cid:{LOGO_CID}" width="32" height="32" alt="LACUNA" style="display:block;border-radius:8px"></td>'
            if logo_png() else "")
    body = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light only"><title>{e(subject)}</title><style>body{{margin:0}} u+.body .gm-screen{{background:#000;mix-blend-mode:screen}} u+.body .gm-diff{{background:#000;mix-blend-mode:difference}} @media (max-width:620px){{.wrap{{width:100%!important}} .pad{{padding-left:24px!important;padding-right:24px!important}}}}</style></head>
<body class="body" style="margin:0;padding:0;background:#f1f1f6"><div style="display:none;max-height:0;overflow:hidden">{e(lead)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f1f6"><tr><td align="center" style="padding:40px 12px">
<table class="wrap" role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:560px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 40px rgba(9,11,31,.12)">
<tr><td class="pad" style="background:#0b0e26;background-image:radial-gradient(120% 140% at 85% 0%,#2a1f5c 0%,#0b0e26 55%);padding:24px 40px">
 <table role="presentation" cellpadding="0" cellspacing="0"><tr>{logo}
 <td style="padding-left:{10 if logo else 0}px;font:700 13px {SANS};letter-spacing:3px;color:#ffffff">{white("LACUNA")} <span style="font-weight:400;color:#9aa0c8">STUDIO</span></td></tr></table>
</td></tr>
<tr><td class="pad" style="padding:32px 40px 8px">
 <div style="font:700 22px/1.4 {SANS};color:#14162e">{e(subject)}</div>
 <p style="margin:12px 0 20px;font:15px/1.7 {SANS};color:#3a3d55">{e(lead)}</p>
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-bottom:1px solid #ececf3">{row_html}</table>
 <p style="margin:20px 0 0;font:14px/1.7 {SANS};color:#3a3d55">{e(note)}</p>
 <table role="presentation" cellpadding="0" cellspacing="0" style="margin:24px 0 8px"><tr><td style="border-radius:999px;background:#df4a22;background-image:linear-gradient(90deg,#df4a22,#d93366 55%,#8f45f0)">
  <a href="{e(link, quote=True)}" style="display:inline-block;padding:12px 30px;font:600 15px {SANS};color:#ffffff;text-decoration:none">{white(e(button))}</a></td></tr></table>
</td></tr>
<tr><td class="pad" style="padding:24px 40px 30px">
 <div style="border-top:1px solid #ececf3;padding-top:18px;font:italic 13px {SERIF};color:#5a5d78">Mind the gaps. Keep the voice.</div>
 <div style="margin-top:8px;font:12px {SANS};color:#a0a3b8">LACUNA Studio · lacunastudio.app</div>
</td></tr></table>
</td></tr></table></body></html>"""
    return {"subject": subject, "text": text, "html": body}


def new_device(email: str, device: str, when: str, where: str | None, link: str) -> dict:
    rows = [(tr("时间"), when), (tr("设备"), device)] + ([(tr("大致位置"), where)] if where else [])
    return render(tr("新设备登录了你的 LACUNA 账号"),
                  tr("有人刚刚在一台新设备上登录了 {email}。", email=email), rows,
                  tr("检查登录设备"), link,
                  tr("是你本人就不用管。不是你的话，马上改密码，并在 设置 → 账号与安全 里退出这台设备。"))


def access_request(email: str, show: str, note: str, link: str) -> dict:
    rows = [(tr("邮箱"), email), (tr("节目"), show or "—")] + ([(tr("想用 LACUNA 做什么"), note)] if note else [])
    return render(tr("新的试用申请：{email}", email=email),
                  tr("有人在登录页申请试用 LACUNA。"), rows, tr("去发邀请"), link,
                  tr("在 设置 → 成员与邀请 → 试用申请 里一键发邀请或忽略。"))
