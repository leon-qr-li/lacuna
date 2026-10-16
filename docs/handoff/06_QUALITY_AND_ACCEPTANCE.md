# Engineering Quality, Evaluation and Acceptance

## Ownership

**Claude Code is accountable for software QA and engineering quality**: test design, implementation, automated regression, bug reproduction, reliability and reporting. The user is a creator/product owner and should not be expected to write/run test suites or manually verify every technical detail. User involvement is for editorial taste and UX acceptance, with focused demos.

## Testing layers

1. **Unit:** EDL operations, time-range arithmetic, track alignment, source provenance, rule precedence, asset indexing, job dependencies, cancellation, cache invalidation, metadata state transitions.
2. **Integration:** ingest -> ASR/align -> plan -> render -> review -> commit -> export; simulate missing assets and resume, crash/restart, stale cache, corrupted media, auth expiration.
3. **Audio golden tests:** synthetic dual tracks with known overlaps, offset/drift, silent gaps, clipping, speech interruptions, inserted music, different sample rates; compare expected alignment, render lengths, audio continuity and no lost speech.
4. **Historical holdout:** reserve unseen raw/final episodes. Evaluate meaningful edit decisions against user-approved reference and listening assessment; exact EDL equality is not the objective.
5. **UI E2E:** episode creation, player 1×/1.5× position/pitch, pause/seek, full listen/edit review switch, time-anchored chat feedback, localized preview, approve/undo, task status, missing asset inbox, candidate rule approval.
6. **Cross-platform:** Windows/macOS install, file paths, FFmpeg invocation, permissions, audio decoding, local model backend fallbacks, cleanup/uninstall/update safety.
7. **Security/data:** immutable originals, no unintended network upload, local-only binding, path traversal protection, command execution safety, user asset backups and no unexpected billing.

## Editorial quality rubric

Evaluate on 1–5 scales with concrete audio evidence:
- Naturalness and personality retained.
- Distracting stumbles removed without over-editing.
- No fabricated words or semantic changes.
- Dual-host overlap/interruptions handled naturally.
- Logical continuity and callbacks preserved.
- Speech intelligibility, loudness and transition quality.
- Music/samples appropriate and not masking speech.
- Ease of correction/undo and confidence in changes.

Track **false-positive deletions** as high-severity editorial failures; flag uncertain changes for review. A transcript-only similarity score is insufficient.

## Product acceptance

**Vertical slice must demonstrate**:

- Two-track local import, complete-episode context pass and non-destructive edit plan.
- First-cut audio with clear source provenance and reversible edits.
- Continuous full-episode player (1×/1.5×), edit-focused review and contextual A/B.
- Time-anchored chat instruction -> localized render -> preview -> explicit approve -> commit; undo.
- Missing asset task does not block unrelated work.
- Data survives restart; original audio unchanged.
- Automated test suite and evidence of passing tests on supported platforms or clearly documented platform gaps.

**Product outcome target**: ~2h raw -> 1–2h active human time, <=3h upper target, negligible manual micro-editing. These are goals requiring actual user trials, **not guaranteed claims**. Measure machine time separately.

## Definition of done

- Feature works in realistic sample, automated tests pass, errors/retries handled, data model documented, reversible and observable, cross-platform behavior considered, and no unverified capabilities claimed.
- Major architecture or dependency decision has a recorded rationale and rollback path.
- User-facing creative flow demonstrated with real sample, not only mock data.
