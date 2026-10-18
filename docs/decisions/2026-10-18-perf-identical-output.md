# Performance work keeps outputs byte-identical (2026-10-18)

**Decision.** A speed-up is accepted only if every output that can be compared is unchanged byte
for byte: ASR JSON, tokens, features, the editor document sent to the AI, AI ops, API JSON, and the
exported WAV/MP3. Parallelism is the main tool (independent work on threads where the native
library releases the GIL), not cheaper maths: a smaller FFT for the pitch tracker or another FFT
library was faster but moved floating-point bits, which could shift a rounded number in the AI
editor's input, so it was rejected.

**Consequences.**
- ASR runs Paraformer and SenseVoice on the same segment at the same time, each with the thread
  count it had; results are identical (checked on a 73.5-min pair).
- Pitch and true-peak work is split into blocks whose per-row results do not depend on the block
  (tests compare the blocked result with one call).
- Every such PR states before/after numbers and how identity was checked (docs/status/perf.md).
