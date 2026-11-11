# 一键修复曲名和作者 — status

- 2026-10-30: built (decision `2026-10-30-credit-fix`). Endpoints `GET/POST/DELETE /api/library/credit-fix`,
  `POST /api/library/credit-fix/apply` (`episode` = that episode's own music; none = shared music).
- Cost per click not measured yet with the real API (estimate $0.3–1 for 6–10 tracks); logged as
  `kind: credit_fix` in the usage log, check after Leon's first real use.
- Open: none.
