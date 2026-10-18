# One loading language for the whole app

Date: 2026-10-17 · Asked by Leon ("任何环节的 loading，我要一个统一的 loading indicator … 即使是这种（0.5 秒）我也要")

Leon picked style **A「声波」** out of three mockups (`/mnt/project-files/lacuna/screenshots/loading/`):
five bouncing level-meter bars as the mark, the brand gradient, placeholders with a moving sheen.

Rules (code: `web/src/features/loading/Loading.tsx`):
1. **Page or tab whose data is on its way** → `PageLoading`: the large wave, "正在打开…" naming the page, and grey
   shapes of what will appear. Shown at once, however short the wait; never a blank page. Lists use shapes of
   their own rows (home: `EpisodeListSkeleton`).
2. **Action that takes seconds** (AI chat reply, Claude lookup, A/B render, dictation) → the small `Wave` where
   it happens: inside the button (`BusyLabel`, label stays) or a `Waiting` row with time used.
3. **Long job** (import + AI first cut, export, publish pack, poster, update download) → `JobProgress`: steps
   when known, a bar (fills with real progress, slides when unknown), time used and "预计还要": extrapolated from
   progress when the job reports it, else from how long it usually takes; over that, "比平时久一点，还在做".
4. **Anything the person started** (every non-GET request through `req`) also moves a 2 px gradient line at the top
   of the window (`TopLine`, mounted by the loading feature's nav entry; page loads move it too).

Alternatives not taken: B 光环 (ring + %), C 静点 (three dots + segmented bar). A global "any request" spinner was
rejected: polls are GETs every second and would make it flicker forever.

New screens follow these rules: import from `features/loading/Loading`, no bare "加载中…" text.

Changed by: `2026-10-17-loading-logo` — the look is now style C「信号」 (logo pulse line); the rules and the component API above are unchanged.
