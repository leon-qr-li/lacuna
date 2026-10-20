import type { Album } from "./api";

// an album without a cover of its own gets one of these, always the same for the same album
const GRADS = [
  "linear-gradient(135deg, #df4a22, #d93366 60%, #8f45f0)",
  "linear-gradient(135deg, #1f3c88, #4677f0 60%, #7fb2ff)",
  "linear-gradient(135deg, #0a734d, #2fb38a 60%, #b6e8c8)",
  "linear-gradient(135deg, #8146d6, #b882ff 60%, #f2c6ff)",
  "linear-gradient(135deg, #9e5000, #e8622a 60%, #ffc7a8)",
];

function grad(id: string): string {
  let h = 0;
  for (const c of id) h = (h * 31 + c.charCodeAt(0)) >>> 0;
  return GRADS[h % GRADS.length];
}

/** The album's cover, or its gradient with the first letter of its name. */
export function AlbumCover({ a, size = 56 }: { a: Pick<Album, "id" | "name" | "cover_url">; size?: number }) {
  const style = { width: size, height: size, borderRadius: Math.round(size * 0.2) };
  if (a.cover_url) return <img className="alb-cover" src={a.cover_url} alt="" style={style} />;
  return (
    <span className="alb-cover alb-cover-grad" aria-hidden="true" style={{ ...style, background: grad(a.id), fontSize: Math.round(size * 0.4) }}>
      {a.name.replace(/^[^\p{L}\p{N}]+/u, "").slice(0, 1)}
    </span>
  );
}
