# The show belongs to the workspace: show profile

**Date:** 2026-10-19 · **Asked by:** Leon ("把我的私人化的东西 … 变成一个完全商用化的转变", top priority)

## Decision
- Everything that was written into the code for 《洛城二三事》 (show name, the hosts Leon and Pei, their track
  letters L / P, colours, how strictly each one is edited, the show-notes footer, the 喜马拉雅 album) is now a
  per-workspace **show profile**, `<workspace>/show.json` (`lacuna_app/show.py`, API `GET/PUT /api/show`,
  page 「节目设置」 `#/show`). It is a separate object from the learned rules, so either can later be shared or
  copied on its own (Leon's 05:48Z ideas: sharing, community; not built).
- **Leon's workspace does not change.** A workspace without the file that is the installation's own folder
  (or already has episodes) is Leon's show (`show.LEGACY`, flag `legacy`), and every AI prompt keeps its exact
  EP001-tuned wording for it (checked against main by hashes while building; kept by
  `tests/app/test_show_prompts.py`). Editing the profile on his workspace keeps the flag.
- **A new workspace starts empty** (`Spaces.create` writes `show.LEGACY`'s blank twin `NEW`): the home page
  asks for the show name and at least one host before the first import.
- **1 to 6 hosts.** Each host has a fixed one-letter tag (token ids `<tag>000123`; Leon L, Pei P, new hosts
  A–Z without I, O, L, P), a name (the track name), a colour from six AA-checked pairs, a strictness
  (gentle / normal / firm) and free-text style notes. Imports take one track per host.
- **AI prompts for other shows** use the same prompts with the show's own name, description, hosts and
  per-host strictness, speak of "the editor" instead of Leon, and the first cut starts from LACUNA's
  conservative defaults (`prompts/first_cut_defaults.txt`) instead of Leon's EP001 calibration; the show's
  own learned rules are appended as before.
- Brand stays LACUNA; the interface never names the AI vendor (unchanged).

## Not in this step
Film-specific publish-pack fields (films / shows) stay, with the prompt told to use them for whatever the
show discusses; per-language engines (zh only); sharing profiles or habits between workspaces.
