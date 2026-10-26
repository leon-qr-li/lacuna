"""The mail someone gets when the owner makes them a LACUNA admin, design C 「权限对照卡」 (Leon 2026-10-26): a
night-sky header (logo, kicker, "<owner> 邀请你成为 LACUNA 管理员"), one line on what it means, two side-by-side
cards (what an admin can do / what only the owner can), the three steps into the admin, the two buttons (后台,
正式站) and the plain links. Same table-and-inline-style build as the invite mail (lacuna_app/invite_mail.py), in
the person's language (``speaking``); the plain-text part says the same."""
from __future__ import annotations

import html

from .i18n import tr
from .invite_mail import LOGO_CID, SANS, SERIF, inline_logo, logo_png, unique_marks, who_of


def render(owner: str, admin_url: str, main_url: str, owner_name: str | None = None, invite_link: str | None = None) -> dict:
    """{"subject", "text", "html", "inline"} in the current ``tr`` language. `invite_link`: they have no account yet
    (the owner invited them as an admin, Leon 2026-10-26): the main button is 接受邀请, the steps start with signing up."""
    e = html.escape
    who = (owner_name or "").strip() or who_of(owner)
    subject = tr("{who} 邀请你成为 LACUNA 管理员", who=who)
    kicker = tr("ADMIN · 管理员邀请")
    lead = tr("和站长一起照看整个网站。你自己的节目和账号都不变。")
    can_title, can = tr("你可以"), [tr("看所有用户和用量"), tr("邀请、停用、删除成员"), tr("处理和回复反馈"), tr("看数据、告警、操作日志")]
    owner_title, owner_only = tr("只有站长能做"), [tr("批时长、改额度"), tr("AI 预算和维护模式"), tr("彻底删除"), tr("任命管理员")]
    no_audio = tr("后台看不到任何音频和逐字稿。")
    if invite_link:
        steps_title = tr("开始之前，三步")
        steps = [tr("点「接受邀请」，设好密码"), tr("用手机验证器 App 扫码，开好两步验证"), tr("打开后台，在门禁页填你的邮箱，收邮箱验证码")]
    else:
        steps_title = tr("第一次进后台，三步")
        steps = [tr("打开后台，在门禁页填你的邮箱，收邮箱验证码"), tr("用 LACUNA 的账号密码登录"), tr("输入手机验证器上的 6 位码")]
    # the main button: the sign-up link, else the admin; the second: the admin, else the site
    first_url, first_label = (invite_link, tr("接受邀请")) if invite_link else (admin_url, tr("打开后台"))
    second_url, second_label = (admin_url, tr("打开后台")) if invite_link else (main_url, tr("打开 LACUNA"))
    expiry = tr("邀请链接 7 天内有效，只能用一次。") if invite_link else ""
    admin_word, main_word = tr("后台"), tr("正式站")
    session = tr("后台登录 8 小时后自动退出，每次登录站长都会收到提醒。")
    ignore = tr("不是你本人？忽略这封邮件即可。")
    host = lambda u: u.split("://", 1)[-1].rstrip("/")

    text = "\n\n".join([
        subject, lead,
        can_title + "\n" + "\n".join(f"- {x}" for x in can),
        owner_title + "\n" + "\n".join(f"- {x}" for x in owner_only),
        no_audio,
        steps_title + "\n" + "\n".join(f"{i}. {x}" for i, x in enumerate(steps, 1)),
        (f"{first_label}: {invite_link}\n{expiry}\n\n" if invite_link else "") + f"{admin_word}: {admin_url}\n{main_word}: {main_url}",
        session, ignore])

    logo = (f'<img src="cid:{LOGO_CID}" width="44" height="44" alt="LACUNA" style="display:block;margin:0 auto;border-radius:11px">'
            if logo_png() else "")
    items = lambda xs: "".join(f'<li style="margin:0">{e(x)}</li>' for x in xs)
    num = lambda i: (f'<td width="32" valign="top" style="padding:0 0 10px"><div style="width:22px;height:22px;border-radius:11px;'
                     f'background:#fff1ea;font:700 12px/22px {SANS};color:#c2410c;text-align:center">{i}</div></td>')
    steps_html = "".join(f'<tr>{num(i)}<td valign="top" style="padding:1px 0 10px;font:14px/1.5 {SANS};color:#14162e">{e(x)}</td></tr>'
                         for i, x in enumerate(steps, 1))
    body = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light only"><title>{e(subject)}</title><style>body{{margin:0}} @media (max-width:620px){{.wrap{{width:100%!important}} .pad{{padding-left:20px!important;padding-right:20px!important}} .col{{display:block!important;width:100%!important;padding:0 0 12px!important}} .bt{{display:block!important}} .gap{{display:block!important;width:auto!important}}}}</style></head>
<body style="margin:0;padding:0;background:#f1f1f6"><div style="display:none;max-height:0;overflow:hidden">{e(lead)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f1f6"><tr><td align="center" style="padding:24px 12px">
<table class="wrap" role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 40px rgba(9,11,31,.12)">
<tr><td class="pad" align="center" style="background:#0b0e26;background-image:radial-gradient(120% 160% at 15% 0%,#3a1f4c 0%,#0b0e26 60%);padding:30px 40px 28px">
 {logo}
 <div style="margin-top:14px;font:600 11px {SANS};letter-spacing:3px;color:#ffb48c">{e(kicker)}</div>
 <div style="margin-top:10px;font:700 25px/1.35 {SANS};color:#ffffff">{e(subject)}</div>
 <div style="width:120px;height:2px;margin:18px auto 0;background:#FF7A3D;background-image:linear-gradient(90deg,#FFC24B 0%,#FF7A3D 40%,#FF4F7B 75%,#A35CFF 100%);border-radius:2px;line-height:2px;font-size:0">&nbsp;</div>
</td></tr>
<tr><td class="pad" style="padding:28px 36px 32px">
 <p style="margin:0;font:14.5px/1.7 {SANS};color:#2b2e4a;text-align:center">{e(lead)}</p>
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:22px 0 0"><tr>
  <td class="col" width="50%" valign="top" style="padding:0 6px 0 0"><div style="border-radius:14px;background:#f1faf5;border:1px solid #cfeedd;padding:16px 18px">
   <div style="font:700 13px {SANS};color:#11683f">&#10003; {e(can_title)}</div>
   <ul style="margin:10px 0 0;padding-left:18px;font:13.5px/1.85 {SANS};color:#1f3b2d">{items(can)}</ul></div></td>
  <td class="col" width="50%" valign="top" style="padding:0 0 0 6px"><div style="border-radius:14px;background:#f6f6fa;border:1px solid #e3e4ee;padding:16px 18px">
   <div style="font:700 13px {SANS};color:#4a4d68">{e(owner_title)}</div>
   <ul style="margin:10px 0 0;padding-left:18px;font:13.5px/1.85 {SANS};color:#4a4d68">{items(owner_only)}</ul></div></td>
 </tr></table>
 <p style="margin:12px 0 0;font:12.5px {SANS};color:#6a6d88;text-align:center">{e(no_audio)}</p>
 <div style="margin-top:22px;font:700 13px {SANS};letter-spacing:1.5px;color:#c2410c">{e(steps_title)}</div>
 <table role="presentation" cellpadding="0" cellspacing="0" style="margin:10px 0 0">{steps_html}</table>
 <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:16px auto 0"><tr>
  <td class="bt" align="center" style="border-radius:999px;background:#df4a22;background-image:linear-gradient(90deg,#df4a22,#d93366 55%,#8f45f0)"><a href="{e(first_url, quote=True)}" class="b1" style="display:inline-block;padding:13px 30px;font:600 15px {SANS};color:#ffffff;text-decoration:none;white-space:nowrap">{e(first_label)} &rarr;</a></td>
  <td class="gap" width="12" height="10"></td>
  <td class="bt" align="center" style="border-radius:999px;border:2px solid #d9dbe8"><a href="{e(second_url, quote=True)}" class="b2" style="display:inline-block;padding:11px 26px;font:600 15px {SANS};color:#14162e;text-decoration:none;white-space:nowrap">{e(second_label)}</a></td>
 </tr></table>
{f'<p style="margin:10px 0 0;font:12.5px {SANS};color:#8a8da6;text-align:center">{e(expiry)}<br>{e(tr("按钮打不开？复制链接："))} <a href="{e(invite_link, quote=True)}" style="color:#b8460f;word-break:break-all">{e(invite_link)}</a></p>' if invite_link else ""}
 <div style="margin-top:26px;padding-top:14px;border-top:1px solid #ececf3;font:12px/1.7 {SANS};color:#8a8da6;text-align:center">{e(admin_word)} <a href="{e(admin_url, quote=True)}" style="color:#b8460f">{e(host(admin_url))}</a> · {e(main_word)} <a href="{e(main_url, quote=True)}" style="color:#b8460f">{e(host(main_url))}</a><br>{e(session)}<br><i style="font-family:{SERIF};color:#5a5d78">Mind the gaps. Keep the voice.</i> · {e(ignore)}</div>
</td></tr></table>
</td></tr></table></body></html>"""
    return {"subject": subject, "text": text, "html": unique_marks(body), "inline": inline_logo()}
