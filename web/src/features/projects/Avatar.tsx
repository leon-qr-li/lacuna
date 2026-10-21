import type { MySpace } from "../spaces/api";

/** A project's square picture, or its own solid colour with the first letter of its name. */
export function ProjectAvatar({ p, size = 56 }: { p: Pick<MySpace, "name" | "color" | "picture">; size?: number }) {
  const style = { width: size, height: size, borderRadius: Math.max(4, Math.round(size * 0.2)) };
  if (p.picture) return <img className="prj-pic" src={p.picture} alt="" style={style} data-testid="project-picture" />;
  return (
    <span
      className="prj-pic prj-pic-color"
      aria-hidden="true"
      style={{ ...style, background: p.color ?? "var(--accent)", fontSize: Math.round(size * 0.42) }}
      data-testid="project-color"
    >
      {p.name.replace(/^[^\p{L}\p{N}]+/u, "").slice(0, 1).toUpperCase()}
    </span>
  );
}
