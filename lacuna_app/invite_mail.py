"""The invite email, design A 「夜航信笺」 (Leon 2026-10-20): a night-sky header with the glowing logo and the
sunset line, then a white letter with who invites you, the six steps of an episode (copy A 「六步流程」, 2026-10-21), to which project and as what, a gradient 接受邀请 button,
the 7-day note, the plain link and the slogan. Table layout with inline styles so Gmail, Outlook and phone mail
apps show it alike; the logo goes along as an inline image (cid:), never as a link to the site, which sits
behind sign-in. Chinese or English (``speaking``), as the inviter picked; the plain-text part says the same."""
from __future__ import annotations

import html
import secrets
from functools import lru_cache

from .i18n import tr

LOGO_CID = "lacuna-logo"

# web/src/features/brand/logo.svg (logo V3 「光晕」)
LOGO_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><defs>
<linearGradient id="lcbg" x1="0" y1="2" x2="0" y2="62" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#161B45"/><stop offset="1" stop-color="#090B1F"/></linearGradient>
<linearGradient id="lcln" x1="14" y1="0" x2="51" y2="0" gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#FFC24B"/><stop offset="0.4" stop-color="#FF7A3D"/><stop offset="0.75" stop-color="#FF4F7B"/><stop offset="1" stop-color="#A35CFF"/></linearGradient>
<clipPath id="lcclip"><rect x="2" y="2" width="60" height="60" rx="15"/></clipPath>
<filter id="lcgl" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="2.0"/></filter></defs>
<g clip-path="url(#lcclip)"><rect width="64" height="64" fill="url(#lcbg)"/>
<g filter="url(#lcgl)" opacity="0.85"><path d="M14 19 V38 H22 L31 16 L40 48 L45 38 H51" fill="none" stroke="url(#lcln)" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></g>
<path d="M14 19 V38 H22 L31 16 L40 48 L45 38 H51" fill="none" stroke="url(#lcln)" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="48" cy="19" r="5.5" fill="#FF4F5E" opacity="0.45" filter="url(#lcgl)"/><circle cx="48" cy="19" r="3" fill="#FF6A6A"/><circle cx="47.2" cy="18.2" r="1" fill="#FFD9D9"/></g></svg>"""

SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei','Helvetica Neue',Arial,sans-serif"
SERIF = "'Iowan Old Style','Songti SC','Noto Serif SC',Georgia,'Times New Roman',serif"


@lru_cache(maxsize=1)
def logo_png() -> bytes | None:
    """The logo as an 96 px PNG (2x for 48 px), or None when it can't be drawn (the mail goes without it)."""
    try:
        from .poster import render_png
        return bytes(render_png(LOGO_SVG, 96))
    except Exception:          # noqa: BLE001 - a logo never stops an invite
        return None


def space_role_label(role: str | None) -> str:
    return {"admin": tr("管理员"), "editor": tr("剪辑师"), "viewer": tr("只听")}.get(role or "", "")


def who_of(email: str) -> str:
    """How the inviter is named in the heading: the part of the address before @ (leon -> Leon)."""
    name = email.split("@", 1)[0] or email
    return name[:1].upper() + name[1:] if name[:1].isascii() else name


HEAD_CID = "lacuna-head"
HEAD_W, HEAD_PAD = 600, 48
CJK_FONT_DIRS = ("/usr/share/fonts/opentype/noto", "/usr/share/fonts/noto-cjk", "/usr/share/fonts/google-noto-cjk")


def _cjk_fonts() -> list[str]:
    """Noto Sans CJK's files (the Docker image installs fonts-noto-cjk; only the sans ones, so resvg never falls
    back to the serif), or [] when there are none."""
    from pathlib import Path
    for d in CJK_FONT_DIRS:
        files = sorted(str(f) for f in Path(d).glob("NotoSansCJK*"))
        if files:
            return files
    return []


def _png(svg: str, w: int, h: int, fonts: list[str]) -> bytes | None:
    """SVG -> PNG at 2x with Inter and Noto Sans CJK only; None on any failure (the HTML version stands in)."""
    from .poster import FONTS
    try:
        import resvg_py
        return bytes(resvg_py.svg_to_bytes(svg_string=svg, width=w * 2, height=h * 2, skip_system_fonts=True,
                                           font_dirs=[str(FONTS)], font_files=fonts, font_family="Inter",
                                           sans_serif_family="Inter"))
    except Exception:          # noqa: BLE001 - a picture never stops an invite
        return None


def _wrap(text: str, size: float, width: float) -> list[str]:
    """Greedy line breaks by estimated width: CJK a full em, Latin about 0.6 em; Latin words stay whole."""
    import re
    lines: list[str] = []
    for part in text.split("\n"):
        line, w = "", 0.0
        for tok in re.findall(r"[A-Za-z0-9@._'’-]+|\s+|.", part):
            tw = sum(size if ord(c) > 0x2e7f else size * 0.6 for c in tok)
            if line and w + tw > width and not tok.isspace():
                lines.append(line.rstrip())
                line, w = "", 0.0
            if not (tok.isspace() and not line):
                line, w = line + tok, w + tw
        lines.append(line.rstrip())
    return lines


@lru_cache(maxsize=32)
def header_png(title: str, kicker: str) -> bytes | None:
    """The dark header band as one picture (2x): logo, wordmark, sunset rule, kicker and title. Gmail's dark mode
    on phones recolours text (white turned dark on the navy band, Leon 2026-10-21) but never a picture. None when
    it can't be drawn (no CJK font, resvg missing): the mail then uses the HTML header."""
    fonts = _cjk_fonts()
    if not fonts:
        return None
    e = html.escape
    size, lh = 28, 38
    lines = _wrap(title, size, HEAD_W - 2 * HEAD_PAD)
    t0 = 36 + 40 + 28 + 2 + 28 + 12 + 10            # logo row, rule, kicker, gap
    h = t0 + lh * len(lines) + 30
    logo = LOGO_SVG.replace('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">',
                            f'<svg x="{HEAD_PAD}" y="36" width="40" height="40" viewBox="0 0 64 64">')
    sans = "Inter, Noto Sans CJK SC"
    title_svg = "".join(f'<text x="{HEAD_PAD}" y="{t0 + lh * i + 29}" font-size="{size}" font-weight="700" fill="#ffffff">{e(l)}</text>'
                        for i, l in enumerate(lines))
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{HEAD_W}" height="{h}" viewBox="0 0 {HEAD_W} {h}" font-family="{sans}">
<defs><radialGradient id="hbg" cx="{HEAD_W * 0.85}" cy="0" r="{HEAD_W * 1.2}" gradientUnits="userSpaceOnUse">
<stop offset="0" stop-color="#2a1f5c"/><stop offset="0.55" stop-color="#0b0e26"/><stop offset="1" stop-color="#0b0e26"/></radialGradient>
<linearGradient id="hrule" x1="0" x2="1"><stop offset="0" stop-color="#FFC24B"/><stop offset="0.4" stop-color="#FF7A3D"/>
<stop offset="0.75" stop-color="#FF4F7B"/><stop offset="1" stop-color="#A35CFF"/></linearGradient></defs>
<rect width="{HEAD_W}" height="{h}" fill="url(#hbg)"/>{logo}
<text x="{HEAD_PAD + 52}" y="61" font-size="15" letter-spacing="3" fill="#ffffff"><tspan font-weight="700">LACUNA</tspan><tspan fill="#9aa0c8"> STUDIO</tspan></text>
<rect x="{HEAD_PAD}" y="104" width="{HEAD_W - 2 * HEAD_PAD}" height="2" rx="1" fill="url(#hrule)"/>
<text x="{HEAD_PAD}" y="146" font-size="12" font-weight="600" letter-spacing="3" fill="#ffb48c">{e(kicker)}</text>
{title_svg}</svg>"""
    return _png(svg, HEAD_W, h, fonts)


BUTTON_CID = "lacuna-button"


def unique_marks(body: str) -> str:
    """Gmail groups mails with the same subject into one conversation and folds whatever repeats an earlier
    mail into "…" (Leon 2026-10-21: a second invite showed only the dots). A different invisible mark in every
    block makes each mail's content its own, so nothing is folded; readers and screen readers see nothing."""
    nonce = secrets.token_hex(6)
    marks = iter(range(1, 1000))
    mark = lambda: (f'<span style="display:none!important;mso-hide:all;font-size:0;line-height:0;max-height:0;'
                    f'max-width:0;opacity:0;overflow:hidden;color:transparent">{nonce}{next(marks)}</span>')
    for tag in ("<p ", "<td ", "<div "):
        parts = body.split(tag)
        body = parts[0] + "".join(f"{tag}{p.replace('>', '>' + mark(), 1)}" for p in parts[1:])
    return body


@lru_cache(maxsize=8)
def button_png(label: str) -> tuple[bytes, int] | None:
    """The 接受邀请 pill as a picture (2x) and its width in CSS px, for the same reason as the header."""
    fonts = _cjk_fonts()
    if not fonts:
        return None
    text = f"{label} \u2192"
    w = int(sum(16 if ord(c) > 0x2e7f else 10 for c in text) + 80)
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="52" viewBox="0 0 {w} 52" font-family="Inter, Noto Sans CJK SC">
<defs><linearGradient id="bg" x1="0" x2="1"><stop offset="0" stop-color="#df4a22"/><stop offset="0.55" stop-color="#d93366"/><stop offset="1" stop-color="#8f45f0"/></linearGradient></defs>
<rect width="{w}" height="52" rx="26" fill="url(#bg)"/>
<text x="{w / 2}" y="32" text-anchor="middle" font-size="16" font-weight="600" letter-spacing=".5" fill="#ffffff">{html.escape(text)}</text></svg>"""
    png = _png(svg, w, 52, fonts)
    return (png, w) if png else None


def steps() -> list[tuple[str, str]]:
    """Version A 「六步流程」 (Leon 2026-10-21): an episode from import to publish, each step in one line."""
    return [(tr("导入分轨"), tr("每位主持人一条分轨，自动转成文字稿")),
            (tr("LACUNA 初剪"), tr("去掉卡顿、口误和多余的话，留住对话的节奏")),
            (tr("逐处审阅"), tr("每一刀都能试听、能恢复，最后由你拍板")),
            (tr("配乐与响度"), tr("片头片尾、背景音乐，整集响度对齐平台标准")),
            (tr("Show notes 与封面"), tr("按本集内容写好节目介绍和时间轴，配好封面海报")),
            (tr("导出发布"), tr("导出成品音频，带上整套发布资料去上线"))]


def render(inviter: str, link: str, project: str | None = None, role: str | None = None) -> dict:
    """{"subject", "text", "html", "preheader"} in the current ``tr`` language. `project`: the project the
    invite joins (None: the new account gets a project of its own); `role`: their role there."""
    who = who_of(inviter)
    role_label = space_role_label(role) if project else ""
    if project:
        subject = tr("{who} 邀请你加入「{project}」", who=who, project=project)
        lead = (tr("你被邀请以「{role}」身份加入这个节目。", role=role_label) if role_label else tr("你被邀请加入这个节目。"))
    else:
        subject = tr("{who} 邀请你使用 LACUNA", who=who)
        lead = tr("你会有一个自己的节目。")
    about = tr("LACUNA Studio 是一间完整的播客工作室，一期节目从导入录音到发布上线，每一步都在这里完成：")
    flow = steps()
    rows = ([(tr("节目"), project)] if project else []) + ([(tr("你的角色"), role_label)] if role_label else []) + \
        [(tr("邀请人"), inviter)]
    button = tr("接受邀请")
    valid = tr("链接 7 天内有效，只能使用一次。")
    fallback = tr("按钮打不开？把这个链接复制到浏览器：")
    ignore = tr("如果你不认识邀请人，忽略这封邮件即可，不会为你创建任何账号。")
    kicker = tr("邀请函 · INVITATION")
    colon = tr("：")
    text = "\n\n".join([subject, lead + about, "\n".join(f"{i}. {h}{colon}{d}" for i, (h, d) in enumerate(flow, 1)), "\n".join(f"{k}{colon}{v}" for k, v in rows),
                        tr("{button}（{valid}）", button=button, valid=valid) + "\n" + link, ignore, "Mind the gaps. Keep the voice.\nLACUNA Studio · lacunastudio.app"])
    e = html.escape
    title = e(subject).replace("「", "<br>「", 1) if project else e(subject)
    # the dark band and the button as pictures: Gmail's dark mode on phones turns their white text dark
    head = header_png(subject.replace("「", "\n「", 1) if project else subject, kicker)
    btn = button_png(button)
    inline = ([{"filename": "header.png", "content": head, "content_id": HEAD_CID}] if head else []) + \
        ([{"filename": "button.png", "content": btn[0], "content_id": BUTTON_CID}] if btn else [])
    row_html = "".join(
        f'<tr><td style="padding:12px 0;border-top:1px solid #ececf3;font:14px {SANS};color:#8a8da6;width:110px">{e(k)}</td>'
        f'<td style="padding:12px 0;border-top:1px solid #ececf3;font:600 14px {SANS};color:#14162e;word-break:break-all">{e(v)}</td></tr>'
        for k, v in rows)
    steps_html = "".join(
        f'<tr><td valign="top" style="padding:9px 14px 9px 0;width:26px"><div style="width:24px;height:24px;border-radius:12px;background:#fff1ea;font:700 12px/24px {SANS};color:#c2410c;text-align:center">{i}</div></td>'
        f'<td style="padding:9px 0;font:15px/1.6 {SANS};color:#3a3d55"><b style="color:#14162e">{e(h)}</b><br><span style="color:#6b6e88">{e(d)}</span></td></tr>'
        for i, (h, d) in enumerate(flow, 1))
    logo = (f'<td><img src="cid:{LOGO_CID}" width="40" height="40" alt="LACUNA" style="display:block;border-radius:10px"></td>'
            if logo_png() else "")
    header = (f'<tr><td style="padding:0;background:#0b0e26;line-height:0"><img src="cid:{HEAD_CID}" width="600" alt="{e(subject)}" '
              f'style="display:block;width:100%;height:auto;border:0"></td></tr>') if head else f"""<tr><td class="pad" style="background:#0b0e26;background-image:radial-gradient(120% 140% at 85% 0%,#2a1f5c 0%,#0b0e26 55%);padding:36px 48px 32px">
 <table role="presentation" cellpadding="0" cellspacing="0"><tr>{logo}
 <td style="padding-left:{12 if logo else 0}px;font:700 15px {SANS};letter-spacing:3px;color:#ffffff">LACUNA <span style="font-weight:400;color:#9aa0c8">STUDIO</span></td></tr></table>
 <div style="height:2px;margin-top:28px;background:#FF7A3D;background-image:linear-gradient(90deg,#FFC24B 0%,#FF7A3D 40%,#FF4F7B 75%,#A35CFF 100%);border-radius:2px"></div>
 <div style="margin-top:28px;font:600 12px {SANS};letter-spacing:3px;color:#ffb48c">{e(kicker)}</div>
 <div class="h1" style="margin-top:10px;font:700 28px/1.35 {SANS};color:#ffffff">{title}</div>
</td></tr>"""
    button_html = (f' <p style="margin:32px 0 14px"><a href="{e(link, quote=True)}"><img src="cid:{BUTTON_CID}" width="{btn[1]}" height="52" '
                   f'alt="{e(button)}" style="display:block;border:0"></a></p>') if btn else f""" <table role="presentation" cellpadding="0" cellspacing="0" style="margin:32px 0 14px"><tr><td style="border-radius:999px;background:#df4a22;background-image:linear-gradient(90deg,#df4a22,#d93366 55%,#8f45f0)">
  <a href="{e(link, quote=True)}" style="display:inline-block;padding:15px 40px;font:600 16px {SANS};color:#ffffff;text-decoration:none;letter-spacing:.5px">{e(button)} &rarr;</a></td></tr></table>"""
    body = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light only"><title>{e(subject)}</title><style>body{{margin:0}} @media (max-width:620px){{.wrap{{width:100%!important}} .pad{{padding-left:24px!important;padding-right:24px!important}} .h1{{font-size:24px!important}}}}</style></head>
<body style="margin:0;padding:0;background:#f1f1f6"><div style="display:none;max-height:0;overflow:hidden">{e(subject)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f1f6"><tr><td align="center" style="padding:40px 12px">
<table class="wrap" role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 40px rgba(9,11,31,.12)">
{header}
<tr><td class="pad" style="padding:36px 48px 8px">
 <p style="margin:0 0 12px;font:16px/1.75 {SANS};color:#3a3d55">{e(lead + about)}</p>
 <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 24px">{steps_html}</table>
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-bottom:1px solid #ececf3">{row_html}</table>
{button_html}
 <p style="margin:0;font:13px {SANS};color:#8a8da6">{e(valid)}</p>
 <p style="margin:24px 0 0;font:12px/1.6 {SANS};color:#a0a3b8">{e(fallback)}<br><a href="{e(link, quote=True)}" style="color:#b8460f;word-break:break-all">{e(link)}</a></p>
</td></tr>
<tr><td class="pad" style="padding:32px 48px 36px">
 <div style="border-top:1px solid #ececf3;padding-top:22px;font:italic 13px {SERIF};color:#5a5d78">Mind the gaps. Keep the voice.</div>
 <div style="margin-top:10px;font:12px/1.6 {SANS};color:#a0a3b8">{e(ignore)}<br>LACUNA Studio · lacunastudio.app</div>
</td></tr></table>
</td></tr></table></body></html>"""
    return {"subject": subject, "text": text, "html": unique_marks(body), "inline": inline + ([] if head else inline_logo())}


def inline_logo() -> list[dict]:
    """The logo as an inline attachment for ``cid:`` (Resend: content_id)."""
    png = logo_png()
    return [{"filename": "lacuna.png", "content": png, "content_id": LOGO_CID}] if png else []
