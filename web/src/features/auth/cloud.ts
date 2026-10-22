// Is this the cloud server (lacunastudio.app)? Asked once per page load; desktop-era controls
// (folders on "this computer", server paths) are hidden there.
import { useEffect, useState } from "react";
import { authApi } from "./api";

let asked: Promise<boolean> | null = null;
const ask = () => (asked ??= authApi.status().then((s) => s.cloud, () => false));

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
