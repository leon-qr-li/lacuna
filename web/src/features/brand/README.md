# Brand

`logo.svg` is the LACUNA Studio mark (V3「光晕」, picked by Leon 2026-10-17): one pulse line that hides
"L" and "A", sunset gradient on navy, a glowing ON AIR light. It is used by

- the favicon (`web/index.html`),
- the top-bar brand (`.brand::before` in `web/src/styles.css`) and the sign-in brand panel (`.auth-logo i`).

New places reuse the file (CSS `url(...)` or `import logo from "…/brand/logo.svg"`), never a copy.
