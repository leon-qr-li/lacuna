# Editorial Playbook — Core Taste and Editing Semantics

## The single most important principle

> **Preserve the conversation. Polish the delivery.**  
> **Remove awkwardness, not personality.**

The podcast is deliberately casual, like two friends chatting, not scripted film criticism. Off-topic tangents, jokes, callbacks, natural hesitation and colloquial language are often the charm. Avoid making hosts sound like a news anchor or a heavily polished speech.

## Source-faithful editing

The user explicitly corrected an earlier assistant example for **adding words not in the recording**. AI must never introduce words like “还是” or “可能” merely to improve a transcript. No fabricated words or synthetic host speech in V1. Use only existing recorded audio.

**Concrete example:**

Raw illustrative utterance: “我觉得这个电影吧，就是……怎么说呢，我觉得它的这个故事，呃，故事其实挺好的，但是这个节奏，我觉得这个节奏有点问题。”

User-preferred conversational output example: **“我觉得它这个故事其实挺好的，但是这个节奏，这个节奏有点问题。”**

The second “这个节奏” is a natural oral repetition, **not an error**. The goal is to remove distracting awkwardness and involuntary stumbles that make a speaker sound unintentionally inarticulate, not to maximize concision. Do not blindly delete “我觉得”, “怎么说呢”, hedges, laughter or repeated words. Judge with **audio prosody and surrounding context**, not text alone. **When uncertain, prefer retaining** over deleting personality.

## Content edits

- Preserve original conversation order and spontaneous tangents (confirmed **Choice A**); no wholesale reordering into a structured essay/review.
- Understand the entire episode before local edit decisions; apparent repeated topic may be a callback or a new angle.
- Remove genuinely valueless rambling only when the cut does not damage conversational logic or character.
- Review significant content deletions as high-risk; preserve evidence and allow restoration.

## Two-track interruptions — distinctive requirement

1. If Host A interjects with an affirmation or adds genuine value while Host B is speaking, the user sometimes **slides A's track slightly later** so the interjection lands at a natural supportive moment. Preserve the conversational relationship and audio synchronization.
2. If A's interruption is abrupt/rude/valueless, delete it; also consider repairing B's disrupted/stumbled speech so B sounds continuous without the interruption.
3. Never simply flatten the two tracks into one before semantic decisions; preserve original track provenance and relative positions.
4. Check seams, breath continuity, crossfades, room tone, overlap masking and whether moving an interjection makes the dialogue nonsensical.
5. When uncertain, flag the interruption for contextual review rather than over-edit.

## Music roles

- **Series jingle:** User first tells AI that a particular intro is for the 1990s series; store it as a series-specific recurring rule. On subsequent episodes proactively propose/reuse, with override.
- **Transition/interlude music:** recognizable signature film theme or cue matching episode mood, often at normal/prominent volume, not whispered under speech.
- **Underscore/background:** less recognizable ambient film score at very low level under ongoing dialogue; apply sensible level automation/ducking, never mask intelligibility.
- **Dialogue/trailer sample:** user finds/captures locally based on inspiration, humor or a thematic quotation; AI proposes opportunities and inserts user-supplied clip. The user historically uses Audacity to record snippets from locally available film/media playback. **Do not make acquiring or ripping such clips an AI V1 requirement.**
- AI should propose exact music source clip in/out times only after an actual asset is available and analyzed. Ask user for a file when missing, create the destination folder, and take over metadata and processing.

## Collaborative editorial behavior

- AI should have taste, make suggestions and be proactive; not silently perform uncontrolled full-episode creative edits that create more rework.
- Routine cleanup may proceed; consequential creative decisions should be surfaced in meaningful batches and reviewed in context.
- Never block unrelated tasks while waiting for a clip or answer.
- User can give casual natural-language commands such as “这段别加音乐”, “把刚放进去的台词加在这儿，前面留半秒，后面接着笑声”, or “这里把原话恢复一下，停顿短一点”.
- AI owns tagging, normalization, folder creation, source ranges, loudness, and asset/project bookkeeping; user wants to be **extremely hands-off** with operational details.

## Learning hierarchy

1. Episode-scoped instruction: do it here, not everywhere.
2. Series-scoped approved rule: e.g., Nineties Series opening jingle.
3. Global approved rule: e.g., preserve natural repetition.
4. Inferred candidate: evidence-backed pattern from repeated user overrides or historic examples; periodically propose promotion to series/global, do not automatically activate.

For every learned rule store scope, origin (explicit vs inferred), example(s), rationale, approval state, version and ability to revoke. Resolve precedence: explicit episode override > approved series/global defaults > inferred suggestion.

## Anti-goals

- Never optimize solely for information density, word count, silence removal or edit quantity.
- Never remove all pauses, laughs, tangents or natural repetitions.
- Never invent host speech.
- Never turn creative approval into hundreds of clicks.
- Never treat an observed raw/final alignment as proof of the user's intention.
