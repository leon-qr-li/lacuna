// 只听 members (a show's "viewer" role) and archived shows: the server refuses every change (routes/spaces.py), so
// the screens grey out the buttons that change the episode instead of letting them click into an error (batch 8, P2;
// archived shows since batch 9).
import { useProjects } from "../projects/api";

/** Why the show on screen can't be changed by the signed-in person: a 只听 member, an archived show, or null. */
export function useReadOnly(): "viewer" | "archived" | null {
  const cur = useProjects()?.current;
  return cur?.archived ? "archived" : cur?.role === "viewer" ? "viewer" : null;
}

/** The episode on screen can't be changed (a 只听 member, or the show is archived). */
export function useListenOnly(): boolean {
  return useReadOnly() !== null;
}
