# Small changes batch (thread 小改动合集)

Leon collects small UI changes in one thread; they ship together in one PR (branch `claude/project-thread-ig4zob`).

## Items
1. **AI 制作人 open/close** (Leon picked 2026-10-20 16:46Z: version A's button + version B's floating button; mockups in project files `lacuna/screenshots/ai-panel-toggle/`).
   - 「收起 »」 moved from the top bar onto the panel header (`web/src/features/chat-dock/`).
   - Closed: no rail, the editor takes the full width; a floating 「AI 制作人」 button at the bottom right (Full Listen only) reopens it. Open/closed is still remembered (`lacuna.chat`).
   - Windows ≤1100px: the panel slides over the page from the right instead of dropping to the page bottom.
   - Tests: `web/e2e/chat_dock.spec.ts`.

## State
- Item 1 built; PR open, goes to staging after #143 / #149.
