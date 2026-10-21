// API of co-editing (lacuna_app/routes/coedit.py)
import { ep, failure } from "../../api";

export interface Hello {
  /** the episode's version now: higher than the one on screen = someone changed it */
  rev: number;
  /** the other people who have this episode open */
  others: { name: string }[];
}

// a plain fetch, not `req`: a heartbeat every few seconds must not move the activity line
export async function hello(id: string, leaving = false): Promise<Hello> {
  const url = `${ep(id)}/presence`;
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ leaving }),
    keepalive: leaving, // still sent while the page closes
  });
  if (!res.ok) throw await failure(res, url);
  return res.json() as Promise<Hello>;
}
