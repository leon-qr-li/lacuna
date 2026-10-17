# LACUNA Studio

Local-first AI podcast producer for 《洛城二三事》. The audio engine is in `lacuna_core/`. The local web app (FastAPI backend plus a React UI) is in `lacuna_app/` and `web/`. Product and engineering docs are in `docs/`. Start with `CLAUDE.md`.

## Install LACUNA Studio (Windows / macOS, no command line needed)

See **[docs/INSTALL.md](docs/INSTALL.md)**: one installer brings Python, the packages and ffmpeg, adds a
desktop shortcut / `LACUNA.app`, and the app updates itself from GitHub Releases (设置 → 更新并重启),
falling back to the previous version if a new one does not start.

- macOS: `curl -fsSL https://github.com/leon-qr-li/lacuna/releases/latest/download/install.sh | bash`
- Windows: `irm https://github.com/leon-qr-li/lacuna/releases/latest/download/install.ps1 | iex` (or double-click `LACUNA-Setup.cmd`)

## Run from a source checkout (development)

You need **Python 3.12+** and, to build the UI once, **Node.js 20+**. The app binds to `127.0.0.1` only, so it is never exposed on your network.

### 1. Install

With [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv venv
uv pip install -e ".[test]"          # add ",claude" to enable the Claude producer
```

With pip:

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS:  source .venv/bin/activate
pip install -e ".[test]"
```

### 2. Build the UI (once, and again after UI changes)

```bash
cd web
npm ci
npm run build                        # writes web/dist, served by the backend
cd ..
```

### 3. Start

```bash
python -m lacuna_app --workspace "C:\Projects\LACUNA_Workspace"      # Windows
python -m lacuna_app --workspace ~/LACUNA_Workspace                   # macOS
```

The browser opens at <http://127.0.0.1:8765/>. Options:

- `--port N` changes the port.
- `--no-browser` stops the browser from opening.
- `--editor mock|claude|auto` picks the AI producer backend.

The default, `auto`, uses Claude when `ANTHROPIC_API_KEY` is set in your environment and offline rules otherwise. Only text and numbers are sent to the API, never audio.

### Workspace layout

```
<workspace>/episodes/<episode>/episode.json   title, demo flag, optional topics
<workspace>/episodes/<episode>/state.json     edits, history, render recipe (atomic writes, .bak kept)
<workspace>/episodes/<episode>/raw/           original recordings (read-only, never written)
```

### AI first cut (EP001)

```bash
python scripts/make_ai_episode.py --workspace ~/LACUNA_Workspace --raw-dir "<folder with Leon.wav / Pei.wav or 原始双轨_*.wav>" \
    --ops spikes/s5_first_cut/out/ai_v3_full_ops.json          # optional: --start <raw s> --minutes <n>
```

Converts the AI editor's ops (`spikes/s5_first_cut/edit_ops.schema.json`) into reviewable edits (`lacuna_app/ai_cut.py`): token ids map to samples, cut points snap to the nearest quiet spot, `tighten_pause` cuts the excess from the middle of the pause, a one-track `cut` becomes a lift on that track (or a cut on both when the other host is silent there), `slip` moves one track, `keep_flag` becomes an unapplied suggestion. Skipped ops are counted in the script output and in `episode.json` (`ai_report`). Edits needing Leon's judgement (content, confidence < 0.6, or > 1.5 s of speech removed) are listed content first, then by duration; everything else is routine, grouped by category and restorable.

### Demo episode (EP001, 10 minutes)

```bash
python scripts/make_demo_episode.py --workspace ~/LACUNA_Workspace --raw-dir "<folder with 原始双轨_Leon.wav / 原始双轨_Pei.wav>"
```

The cut positions come from Leon's hand edit of EP001. Categories, reasons and confidence are synthesised and labelled as demo data. The raw audio is referenced by path and never copied.

### Using it

- **整集试听 (Full Listen)**
  - Player controls: play/pause (space), ±5 s (←/→), 1× or 1.5× with pitch preserved, and an optional 5 s rewind on pause.
  - Lane view of both tracks around the playhead, plus a "这附近改了什么" list of nearby edits.
  - Chat anchored to the playhead. Try 「停顿短一点」, 「恢复这处」 or 「删掉这句」. Each suggestion lets you preview it A/B, then choose 批准 to approve or 再改 to revise.
- **改动审阅 (Edit Review)**
  - Edits that need your judgement are listed content trims first, then by duration removed. Routine cleanup is summarised by category.
  - For each edit: A/B compare, keep or restore, and the original words.
  - Keyboard: J/K previous/next, space play, A/B switch, R restore.
- **Undo / redo**: the header buttons or Ctrl/Cmd+Z (Shift for redo).

### Tests

```bash
python -m pytest -q tests                      # engine + API (synthetic audio, no network)
cd web && npx playwright test                  # E2E in Chromium; starts its own backend
```

Playwright needs a Chromium build. If you don't have one, run `npx playwright install chromium` once.
