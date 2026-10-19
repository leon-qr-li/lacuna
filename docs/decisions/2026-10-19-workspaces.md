# Content ownership: workspaces

**Date:** 2026-10-19 · **Asked by:** Leon (future direction 1: who owns episodes; cloud with invited beta users)

## Decision
- Episodes, the library (公共 and 本集), learned rules, chat logs and AI usage belong to a **workspace**, never
  to a single account. Everyone in a workspace shares all of it; nobody outside sees any of it.
- A workspace is a complete workspace folder: the installation's own folder is the first one ("main", Leon's
  data, nothing moves), others are `<root>/spaces/<id>/`. A dispatcher (`routes/spaces.py`) sends each API call
  to the signed-in person's current workspace, which runs as its own app on that folder. So no feature needs
  to know about owners, learning evidence keeps its rules (it lives in the workspace and survives episode
  deletes as before), and the 公共 / 本集 scopes work unchanged inside each workspace.
- Roles inside a workspace: 管理 admin (members, rename, delete episodes for good), 剪辑 editor (all editing
  work), 只听 viewer (listen and read; every change answers 403). The site owner and admins (account roles,
  `2026-10-19-invites-roles-2fa.md`) manage every workspace, but only see a workspace's episodes when they are
  a member of it.
- Invites choose the workspace: by default the new person gets **a new workspace of their own** (beta users
  are isolated from each other and from Leon's show); for a co-host (Pei) Leon picks "join 「leon」" with a role.
- On upgrade, existing accounts go into "main" (owner and admins as 管理, others as 剪辑). Deleting an account
  takes it out of every workspace; what it made stays.
- Speech models are one shared copy (`<root>/models`), and the voice-input model is loaded once for all.

## Not in this step
Per-workspace AI spending caps and storage quotas (the usage log is already per workspace); one import at a
time across workspaces on the cloud server (deploy thread); deleting a whole workspace.
