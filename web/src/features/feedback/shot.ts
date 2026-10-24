// The screenshot a 遇到问题 report carries: only LACUNA's own page (drawn from the page itself, not a screen
// capture), without the 反馈 panel and dialogs on top. No sound, no other windows.
import { toJpeg } from "html-to-image";

const SKIP = ["fb-host", "dlg-host", "fb-prompt-host"];

export async function captureApp(): Promise<string | null> {
  try {
    const bg = getComputedStyle(document.body).backgroundColor || "#080a1a";
    return await toJpeg(document.body, {
      quality: 0.82,
      pixelRatio: Math.min(window.devicePixelRatio || 1, 1.5),
      width: window.innerWidth,
      height: window.innerHeight,
      backgroundColor: bg,
      cacheBust: true,
      skipFonts: true, // dozens of font files per picture otherwise; the system font is fine for a report
      filter: (n) => !(n instanceof HTMLElement && SKIP.some((c) => n.classList.contains(c))),
    });
  } catch {
    return null; // some pages can't be drawn: the report goes without a picture
  }
}

/** A picture the person picked instead (换一张图), as a JPEG data URL no wider than 1920 px. */
export async function fromFile(file: File): Promise<string> {
  const url = URL.createObjectURL(file);
  try {
    const img = await load(url);
    const scale = Math.min(1, 1920 / img.naturalWidth);
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * scale);
    c.height = Math.round(img.naturalHeight * scale);
    c.getContext("2d")!.drawImage(img, 0, 0, c.width, c.height);
    return c.toDataURL("image/jpeg", 0.85);
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function load(src: string): Promise<HTMLImageElement> {
  return new Promise((ok, bad) => {
    const img = new Image();
    img.onload = () => ok(img);
    img.onerror = () => bad(new Error("image"));
    img.src = src;
  });
}
