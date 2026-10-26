// 只听 members (a show's "viewer" role): the server refuses every change they try (routes/spaces.py), so the
// screens grey out the buttons that change the episode instead of letting them click into an error (batch 8, P2).
import { useProjects } from "../projects/api";

/** The signed-in person is a 只听 member of the show on screen. */
export function useListenOnly(): boolean {
  const sp = useProjects();
  return sp?.current?.role === "viewer";
}
