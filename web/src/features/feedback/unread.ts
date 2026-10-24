// How many of my feedback items have an answer I haven't looked at (the red dot on 反馈), shared by the
// top-bar button and the panel. Read when the app opens and when the window comes back into focus.
import { useEffect, useState } from "react";
import { authApi } from "../auth/api";
import { feedbackApi } from "./api";

// feedback belongs to an account: an installation without sign-in (a development checkout) shows no 反馈
let signedIn = false;
export const isSignedIn = () => signedIn;
export function useSignedIn() {
  const [on, set] = useState(signedIn);
  useEffect(() => {
    if (signedIn) return;
    authApi.status().then((s) => {
      signedIn = !!s.email;
      set(signedIn);
    }, () => undefined);
  }, []);
  return on;
}

let count = 0;
const subs = new Set<(n: number) => void>();

export function setUnread(n: number) {
  count = n;
  subs.forEach((f) => f(n));
}

let last = 0;
export function refreshUnread() {
  if (Date.now() - last < 30_000) return;
  last = Date.now();
  feedbackApi.mine().then((r) => setUnread(r.unread), () => undefined);
}

/** `refresh`: ask the server now and on focus (the top-bar button); otherwise just follow the count. */
export function useUnread(refresh = true) {
  const [n, set] = useState(count);
  useEffect(() => {
    subs.add(set);
    if (!refresh || !signedIn) return () => void subs.delete(set);
    refreshUnread();
    const focus = () => refreshUnread();
    window.addEventListener("focus", focus);
    return () => {
      subs.delete(set);
      window.removeEventListener("focus", focus);
    };
  }, [refresh]);
  return n;
}
