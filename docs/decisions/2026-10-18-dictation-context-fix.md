# Voice input: fix homophones and names with a context pass (backlog #10)

**Context.** Voice input runs SenseVoice-Small locally, one clip at a time, with no hotwords (sherpa-onnx
SenseVoice has none) and no idea what the show is about. Leon: 「Pei」 comes out as ordinary words,
「为什么」 as 「胃什么」, 「游戏」 as 「油戏」, and 「Leon」 is wrong every time however often he says it.

**Decision.** After the local pass, one small request to Claude Haiku 5.5 (`claude-haiku-5-5`, effort
low, JSON-schema output) corrects the text using context the server already has:
- the hosts (Leon, Pei, the episode's track names) and the names Leon corrected before (`names.json`);
- the episode title and the films / glossary / shows of its publish pack, if one exists;
- the transcript within 40 s of the playhead (chat) and Leon's last 6 chat turns.

The page sends only `episode`, `at` and `where` (chat | poster) with the clip; the server builds the
context. The model may only swap mis-heard words (homophones, names, titles); it must keep wording,
order, tone and fillers. On by default; `LACUNA_DICTATION_FIX=off` turns it off.

**Never worse than before.** No key, a timeout (8 s, no retries), an API error, a refusal, bad JSON or
an answer that rewrote the sentence (character similarity < 0.5) all return the local text unchanged.
The wait is covered by the existing 「识别中…」 indicator.

**Privacy / cost.** Audio never leaves the machine; only the recognised text and the text context
go out. ~2-3 k input tokens per clip on Haiku 5.5 ($0.10 / $0.50 per M): well under $0.001 a clip.

**Rejected.** Hotwords in the recogniser (not supported by SenseVoice in sherpa-onnx; a transducer
model with hotwords would be a second ~200 MB download and slower on CPU); a bigger model for the
pass (latency matters more than depth for a one-line correction).
