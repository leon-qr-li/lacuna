import { useEffect, useRef, useState } from "react";
import type { Episode } from "../../api";
import { api } from "../../api";
import { t } from "../../i18n";
import { hello } from "./api";

export const BEAT_MS = 5000;

/**
 * Several people in one episode (decision 2026-10-21-co-editing-safety-net): says hello every few
 * seconds (and when the tab comes back), keeps the list of who else is here, and when the episode's
 * version went up because of someone else, loads the latest so this screen never works on an old one.
 */
export function useCoedit(id: string, ep: Episode | null, onEpisode: (e: Episode) => void, flash: (m: string) => void) {
  const [others, setOthers] = useState<{ name: string }[]>([]);
  const rev = useRef<number | undefined>(undefined);
  rev.current = ep?.rev;
  const cb = useRef({ onEpisode, flash });
  cb.current = { onEpisode, flash };

  useEffect(() => {
    let alive = true;
    let loading = false;
    const beat = async () => {
      if (document.hidden || loading) return;
      try {
        const h = await hello(id);
        if (!alive) return;
        setOthers(h.others);
        if (rev.current !== undefined && h.rev > rev.current) {
          loading = true;
          const next = await api.episode(id);
          // a change of our own may have answered meanwhile: never go back to an older version
          if (alive && (rev.current === undefined || (next.rev ?? 0) > rev.current)) {
            cb.current.onEpisode(next);
            if (h.others.length) cb.current.flash(t("这一集有新的修改，已更新为最新内容"));
          }
        }
      } catch {
        /* offline for a moment: the next beat tries again */
      } finally {
        loading = false;
      }
    };
    void beat();
    const timer = window.setInterval(() => void beat(), BEAT_MS);
    const onVisible = () => !document.hidden && void beat();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      alive = false;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
      hello(id, true).catch(() => undefined);
    };
  }, [id]);

  return { others };
}
