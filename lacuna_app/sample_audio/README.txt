LACUNA sample show - final product files
========================================

zh\  CosyVoice-300M-SFT (FunAudioLLM, Apache-2.0), built-in speakers only, no cloning:
       host0 小林 = 中文男, host1 阿乔 = 中文女.  Total 94.04 s.
       Lines 1, 3, 4 rendered in pieces so no script word is dropped
       (今天我们 x2, 呃, 我数了); the other 16 lines are the approved single-pass takes.
       preview_zh.mp3 = both tracks mixed (listening only).
en\  Kokoro-82M (hexgrad, Apache-2.0), am_michael (host0 Sam) + af_heart (host1 Alex).  Total 86.51 s.

host0.flac, host1.flac  16 kHz mono 16-bit FLAC, full length, 0.6 s lead, each line followed by its
                        script gap, white noise floor ~-60 dBFS RMS. No cough, no loudness processing.
tokens.json             19 lines: {"host", "start", "end", "tokens": [[text, start, end], ...]}, seconds on
                        the full track. zh tokens = every non-space script character; en = script split on spaces.

Token times: CTC forced alignment of the exact script tokens against each line's audio
  zh: jonatasgrosman/wav2vec2-large-xlsr-53-chinese-zh-cn (Apache-2.0); 饱 呃 煽 碗 are not in its
      vocabulary and were aligned as same-sounding characters (保/饿/扇/晚); the token text stays the script's.
  en: facebook/wav2vec2-base-960h (Apache-2.0).
  Token start = first CTC frame; end = next token's start, or at most 0.25 s after the token's last frame
  before a pause / at line end. Checked: start<end, monotonic, inside the line; en starts match the audio
  onset; cross-checked against Whisper large-v3 word timestamps (all script tokens found, Whisper runs
  ~0.2 s earlier throughout, a known Whisper bias).

Scripts (in ..\): cosy\build_cosy.py, cosy\probe_pieces.py, cosy\assemble_zh.py, build_final.py zh|en,
verify_tokens.py zh|en.
