"""The invite email, design A 「夜航信笺」 (Leon 2026-10-20), compact with the plan card (Leon 2026-10-22: what
the beta gives at the very top, short enough not to scroll): a short night-sky header with the logo, the title and
who sent it, the plan card (or the show they join), the six steps as short titles, a gradient 接受邀请 button,
the authenticator and 7-day note, the plain link and the slogan. Table layout with inline styles so Gmail, Outlook and phone mail
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
    """Version B 「专业名词式」 (Leon 2026-10-23): an episode from import to publish, each step in one line."""
    return [(tr("分轨导入与自动转写"), tr("每位主持人一条分轨，自动转成文字稿")),
            (tr("LACUNA 智能初剪"), tr("去掉卡顿、口误和多余的话，留住对话的节奏")),
            (tr("逐处审阅，A/B 对比"), tr("每一刀都能前后对比试听、能恢复，最后由你拍板")),
            (tr("配乐编排与响度标准化"), tr("片头片尾、背景音乐，整集响度对齐平台标准")),
            (tr("Show notes 与封面生成"), tr("按本集内容写好节目介绍和时间轴，配好封面海报")),
            (tr("多平台导出与发布"), tr("导出成品音频，带上整套发布资料发到各个平台"))]


PLAN_LINES = {
    # the plan card (Leon 2026-10-22, design A 套餐卡): what the new account gets, at the very top
    "trial": (lambda: tr("免费体验 · 1 小时音频"), lambda: tr("一次性试用 · 所有功能都能用")),
    "basic": (lambda: tr("基础版 · 每月 4 小时音频"), lambda: tr("所有功能都能用 · 额度每月重置")),
    "pro": (lambda: tr("专业版 · 每月 12 小时音频"), lambda: tr("所有功能都能用 · 额度每月重置")),
}


@lru_cache(maxsize=32)
def compact_header_png(title: str, kicker: str, sub: str) -> bytes | None:
    """The invite's short dark band as one picture (2x): logo + wordmark with the kicker on the right, the
    sunset rule, the title and who sent it. Same reason as ``header_png``; None falls back to HTML."""
    fonts = _cjk_fonts()
    if not fonts:
        return None
    e = html.escape
    pad, size, lh = 40, 24, 32
    lines = _wrap(title, size, HEAD_W - 2 * pad)
    t0 = 24 + 30 + 18 + 2 + 16
    h = t0 + lh * len(lines) + 4 + 20 + 24
    logo = LOGO_SVG.replace('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">',
                            f'<svg x="{pad}" y="24" width="30" height="30" viewBox="0 0 64 64">')
    title_svg = "".join(f'<text x="{pad}" y="{t0 + lh * i + 24}" font-size="{size}" font-weight="700" fill="#ffffff">{e(l)}</text>'
                        for i, l in enumerate(lines))
    sub_y = t0 + lh * len(lines) + 18
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{HEAD_W}" height="{h}" viewBox="0 0 {HEAD_W} {h}" font-family="Inter, Noto Sans CJK SC">
<defs><radialGradient id="hbg" cx="{HEAD_W * 0.85}" cy="0" r="{HEAD_W * 1.2}" gradientUnits="userSpaceOnUse">
<stop offset="0" stop-color="#2a1f5c"/><stop offset="0.55" stop-color="#0b0e26"/><stop offset="1" stop-color="#0b0e26"/></radialGradient>
<linearGradient id="hrule" x1="0" x2="1"><stop offset="0" stop-color="#FFC24B"/><stop offset="0.4" stop-color="#FF7A3D"/>
<stop offset="0.75" stop-color="#FF4F7B"/><stop offset="1" stop-color="#A35CFF"/></linearGradient></defs>
<rect width="{HEAD_W}" height="{h}" fill="url(#hbg)"/>{logo}
<text x="{pad + 40}" y="44" font-size="13" letter-spacing="3" fill="#ffffff"><tspan font-weight="700">LACUNA</tspan><tspan fill="#9aa0c8"> STUDIO</tspan></text>
<text x="{HEAD_W - pad}" y="44" text-anchor="end" font-size="11" font-weight="600" letter-spacing="2.5" fill="#ffb48c">{e(kicker)}</text>
<rect x="{pad}" y="72" width="{HEAD_W - 2 * pad}" height="2" rx="1" fill="url(#hrule)"/>
{title_svg}<text x="{pad}" y="{sub_y}" font-size="13" fill="#9aa0c8">{e(sub)}</text></svg>"""
    return _png(svg, HEAD_W, h, fonts)


def render(inviter: str, link: str, project: str | None = None, role: str | None = None,
           plan: str | None = None, beta: bool = False, inviter_name: str | None = None) -> dict:
    """{"subject", "text", "html", "inline"} in the current ``tr`` language, compact design A (Leon 2026-10-22:
    the plan at the very top, no scrolling). `project`: the show the invite joins (None: the new account gets a
    show of its own and the plan card says what it includes); `role`: their role there; `beta`: the site is in
    beta (新成员需站长批准 on); `inviter_name`: the name the inviter gave, else the part before @."""
    who = (inviter_name or "").strip() or who_of(inviter)
    role_label = space_role_label(role) if project else ""
    if project:
        subject = tr("{who} 邀请你加入「{project}」", who=who, project=project)
        lead = (tr("你被邀请以「{role}」身份加入这个节目。", role=role_label) if role_label else tr("你被邀请加入这个节目。"))
    else:
        subject = tr("{who} 邀请你使用 LACUNA", who=who)
        lead = tr("你会有一个自己的节目。")
    about = tr("从导入录音到发布上线，一期节目的每一步都在 LACUNA 完成：")
    flow = steps()
    if project:
        card_kicker = tr("你将加入的节目")
        card_title = f"{project} · {role_label}" if role_label else project
        card_sub = tr("用节目主人的套餐和额度，你不用另外付费")
    else:
        line, sub = PLAN_LINES.get(plan or "basic", PLAN_LINES["basic"])
        card_kicker = tr("你的 BETA 套餐") if beta else tr("你的套餐")
        card_title = line()
        card_sub = (tr("beta 期间免费") + " · " + sub()) if beta else sub()
    button = tr("接受邀请")
    note = tr("注册时需要手机上的验证器 App（如 Google Authenticator）。链接 7 天内有效，只能用一次。")
    fallback = tr("按钮打不开？复制链接：")
    ignore = tr("不认识邀请人？忽略这封邮件即可，不会创建账号。")
    kicker = tr("BETA 邀请函") if beta else tr("邀请函 · INVITATION")
    by = tr("邀请人 {email}", email=inviter)
    colon = tr("：")
    text = "\n\n".join([subject, by, f"{card_kicker}{colon}{card_title}\n{card_sub}", lead + about,
                        "\n".join(f"{i}. {h}{colon}{d}" for i, (h, d) in enumerate(flow, 1)),
                        f"{button}\n{link}", note, ignore, "Mind the gaps. Keep the voice.\nLACUNA Studio · lacunastudio.app"])
    e = html.escape
    head = compact_header_png(subject, kicker, by)
    btn = button_png(button)
    inline = ([{"filename": "header.png", "content": head, "content_id": HEAD_CID}] if head else []) + \
        ([{"filename": "button.png", "content": btn[0], "content_id": BUTTON_CID}] if btn else [])
    logo = (f'<td><img src="cid:{LOGO_CID}" width="30" height="30" alt="LACUNA" style="display:block;border-radius:8px"></td>'
            if logo_png() else "")
    header = (f'<tr><td style="padding:0;background:#0b0e26;line-height:0"><img src="cid:{HEAD_CID}" width="600" alt="{e(subject)}" '
              f'style="display:block;width:100%;height:auto;border:0"></td></tr>') if head else f"""<tr><td class="pad" style="background:#0b0e26;background-image:radial-gradient(120% 140% at 85% 0%,#2a1f5c 0%,#0b0e26 55%);padding:24px 40px">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td><table role="presentation" cellpadding="0" cellspacing="0"><tr>{logo}
 <td style="padding-left:{10 if logo else 0}px;font:700 13px {SANS};letter-spacing:3px;color:#ffffff">LACUNA <span style="font-weight:400;color:#9aa0c8">STUDIO</span></td></tr></table></td>
 <td align="right" style="font:600 11px {SANS};letter-spacing:2.5px;color:#ffb48c">{e(kicker)}</td></tr></table>
 <div style="height:2px;margin-top:18px;background:#FF7A3D;background-image:linear-gradient(90deg,#FFC24B 0%,#FF7A3D 40%,#FF4F7B 75%,#A35CFF 100%);border-radius:2px"></div>
 <div class="h1" style="margin-top:16px;font:700 24px/1.3 {SANS};color:#ffffff">{e(subject)}</div>
 <div style="margin-top:4px;font:13px {SANS};color:#9aa0c8">{e(by)}</div>
</td></tr>"""
    card = f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 18px"><tr><td style="border:2px solid #e0336d;border-radius:14px;background:#fff6f2;background-image:linear-gradient(135deg,#fff4ee 0%,#fbeefb 100%);padding:16px 20px">
 <div style="font:700 11px {SANS};letter-spacing:2.5px;color:#c2410c">{e(card_kicker)}</div>
 <div style="margin-top:4px;font:700 22px/1.3 {SANS};color:#14162e">{e(card_title)}</div>
 <div style="margin-top:4px;font:13.5px/1.5 {SANS};color:#5a5d78">{e(card_sub)}</div></td></tr></table>"""
    cells = [f'<td width="50%" style="padding:4px 8px 4px 0;font:14px/1.4 {SANS};color:#14162e"><span style="display:inline-block;width:20px;height:20px;'
             f'border-radius:10px;background:#fff1ea;font:700 11px/20px {SANS};color:#c2410c;text-align:center;margin-right:8px">{i}</span>{e(h)}</td>'
             for i, (h, _) in enumerate(flow, 1)]
    steps_html = "".join(f"<tr>{cells[i]}{cells[i + 1]}</tr>" for i in range(0, len(cells), 2))
    button_html = (f' <p style="margin:0 0 10px"><a href="{e(link, quote=True)}"><img src="cid:{BUTTON_CID}" width="{btn[1]}" height="52" '
                   f'alt="{e(button)}" style="display:block;border:0"></a></p>') if btn else f""" <table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 10px"><tr><td style="border-radius:999px;background:#df4a22;background-image:linear-gradient(90deg,#df4a22,#d93366 55%,#8f45f0)">
  <a href="{e(link, quote=True)}" style="display:inline-block;padding:13px 34px;font:600 15px {SANS};color:#ffffff;text-decoration:none">{e(button)} &rarr;</a></td></tr></table>"""
    body = f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light only"><title>{e(subject)}</title><style>body{{margin:0}} @media (max-width:620px){{.wrap{{width:100%!important}} .pad{{padding-left:22px!important;padding-right:22px!important}} .h1{{font-size:22px!important}}}}</style></head>
<body style="margin:0;padding:0;background:#f1f1f6"><div style="display:none;max-height:0;overflow:hidden">{e(card_title)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f1f6"><tr><td align="center" style="padding:24px 12px">
<table class="wrap" role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:600px;background:#ffffff;border-radius:16px;overflow:hidden;box-shadow:0 8px 40px rgba(9,11,31,.12)">
{header}
<tr><td class="pad" style="padding:24px 40px 26px">
{card}
 <p style="margin:0 0 10px;font:14.5px/1.65 {SANS};color:#3a3d55">{e(lead + about)}</p>
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:0 0 20px">{steps_html}</table>
{button_html}
 <p style="margin:0;font:12.5px/1.6 {SANS};color:#8a8da6">{e(note)}</p>
 <div style="margin-top:18px;padding-top:14px;border-top:1px solid #ececf3;font:11.5px/1.6 {SANS};color:#a0a3b8">{e(fallback)} <a href="{e(link, quote=True)}" style="color:#b8460f;word-break:break-all">{e(link)}</a><br><i style="font-family:{SERIF};color:#5a5d78">Mind the gaps. Keep the voice.</i> · {e(ignore)} · lacunastudio.app</div>
</td></tr></table>
</td></tr></table></body></html>"""
    return {"subject": subject, "text": text, "html": unique_marks(body), "inline": inline + ([] if head else inline_logo())}


def inline_logo() -> list[dict]:
    """The logo as an inline attachment for ``cid:`` (Resend: content_id)."""
    png = logo_png()
    return [{"filename": "lacuna.png", "content": png, "content_id": LOGO_CID}] if png else []
