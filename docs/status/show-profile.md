# Generic show (commercialisation step 1) - 2026-10-19

State: PR #126 (draft), waiting for Leon's validation on the preview site before merge.
Decision: docs/decisions/2026-10-19-show-profile.md

## Done
- `lacuna_app/show.py` + `routes/show.py`: the workspace's show profile (load / save / normalise, LEGACY for
  Leon, NEW for fresh workspaces, prompt helpers `neutral`, `describe_en`, `style_lines`).
- Web `web/src/features/show/`: 「节目设置」 page + first-run setup card on the home page; host colours as CSS
  vars `--host-N`; import form, levels, lessons, upload, music texts use the show's hosts and name.
- Import with 1–6 tracks (`importer.start(..., paths: list)`), features / AI cut / rule cut for N tracks.
- Prompts: chat editor (`editor.system_for`), lessons rewrite + summary (`lessons._for_show`), first cut
  (`first_cut.system_prompt(extra, profile)`, `prompts/first_cut_brief_generic.txt`,
  `prompts/first_cut_defaults.txt`), learned rules (`learning.learn(ds, who)`, `reviewer(ws)`), show notes
  (`publish.notes_intro`), poster (`poster.poster_intro`, `brief_context(show_name)`), music credit lookup
  (`library.lookup_system`), dictation fix (show + people from the profile).
- Tests: `tests/app/test_show.py`, `tests/app/test_show_prompts.py`, new cases in test_import / test_learning,
  `web/e2e/show.spec.ts`.

## Left (later steps, not started)
- Publish pack is still film-shaped (films / shows fields, poster "film elements"); 「上传喜马拉雅」 tab shows
  even when the show doesn't publish there.
- Some labels say 两人 / both for 3+ hosts (review filters); `EXPLICIT_OVERRIDES` and levels `ALIASES` still
  know Pei by name (harmless for other shows); lessons JSON key `leon_said`.
- English ASR / filler detection (future direction 3).
