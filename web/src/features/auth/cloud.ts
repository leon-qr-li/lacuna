// Is this the cloud server (lacunastudio.app)? Asked once per page load; desktop-era controls
// (folders on "this computer", server paths) are hidden there.
import { useEffect, useState } from "react";
import { authApi } from "./api";

let asked: Promise<boolean> | null = null;
// a failed status call is not an answer: forget it and ask again (it once left the cloud showing server folders)
const ask = (): Promise<boolean> =>
  (asked ??= authApi.status().then(
    (s) => s.cloud,
    () => {
      asked = null;
      return new Promise<boolean>((done) => setTimeout(() => void ask().then(done), 2000));
    },
  ));

/** null while unknown, then whether the app runs in the cloud. */
export function useCloud(): boolean | null {
  const [cloud, setCloud] = useState<boolean | null>(null);
  useEffect(() => {
    let live = true;
    void ask().then((c) => live && setCloud(c));
    return () => {
      live = false;
    };
  }, []);
  return cloud;
}
