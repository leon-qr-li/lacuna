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
uv pip install -e ".[test,claude,asr]"   # claude = AI producer (Claude API), asr = import (sherpa-onnx)
```

With pip:

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate      macOS:  source .venv/bin/activate
pip install -e ".[test,claude,asr]"
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

Sign in (local account), then 剧集 lists the episodes (archive / restore / delete; deleting never removes learned habits). 导入新一集 takes the two per-host tracks (drag & drop or pick files) and runs ASR, analysis, volume leveling and the AI first cut in the background, with progress and time left.

Each episode is one flow: **审阅改动 → 整集试听 → 声音 → 本集学到的规则 → 配乐 → 导出 → 发布** (发布资料 / 喜马拉雅版 / 海报 / 上传喜马拉雅).

- **审阅改动 (Edit Review)**: edits that need your judgement, in time order. Each preview plays the cut with 5 s either side; A/B original vs. cut, keep or restore, 剩下全部通过 (one undoable step), 只看没过目的, 带配乐听. Keys: Space play, ←/→ previous/next, K keep, R restore, A/B, S speed (1× → 1.25× → 1.5× → 2×), ? help.
- **整集试听 (Full Listen)**: play/pause (Space), ±5 s (←/→), 1× / 1.5× with pitch preserved, optional 5 s rewind on pause; lane view of both tracks, "这附近改了什么"; the AI producer chat (called LACUNA) anchored to the playhead, e.g. 「停顿短一点」「删掉这句」「Pei 声音大一点」. Each suggestion can be previewed, then 批准 or 再改; 「记住」 turns a long-term ask into a rule after you confirm LACUNA's rewording. Voice input transcribes locally.
- **声音**: both hosts are evened out at import (each host's speech at -20 LUFS); per-track ±1 dB, 重新统一, clipping report.
- **本集学到的规则**: what this episode taught (kept / restored edits, chat asks) as candidate rules; nothing is stored until you confirm. All rules live on 学到的规则 (top bar).
- **配乐**: place library music as 片头 / 间奏 / 片尾 / 铺底 / 台词; background defaults to 22 dB under full level, beds fill gaps automatically and loop, one player synced with the strip. Music files live in 素材库.
- **导出**: WAV + MP3 mastered to -16 LUFS / -1 dBTP into `<workspace>/exports/<episode>/`.
- **发布**: title candidates, summary and show notes (no tables), a 喜马拉雅版 tab with three layouts, 2×2 poster versions with 一句话改, and an upload page that follows 喜马拉雅's form order (Leon uploads by hand).
- **Undo / redo**: the header buttons or Ctrl/Cmd+Z (Shift for redo). Confirmations use the in-app dialog.

### Tests

```bash
python -m pytest -q tests                      # engine + API (synthetic audio, no network)
cd web && npx playwright test                  # E2E in Chromium; starts its own backend
```

Playwright needs a Chromium build. If you don't have one, run `npx playwright install chromium` once.
