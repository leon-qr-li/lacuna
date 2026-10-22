# New-user experience (batch 新用户体验)

Date: 2026-10-22 · Decided by Leon ("全按你推荐的走", 18:10Z); report https://claude.ai/artifact/RMNusRUSCYcRVGBcn5uhLG

- **Guide = sample episode + checklist (C + A).** A new account's 首页 is a welcome page ("欢迎，Sam") until its first
  show is set up: try LACUNA 示例节目, or set up my show. The 入门清单 (show → import → review ≥3 → ask LACUNA once
  → intro + outro → download) ticks itself from real actions; progress is per person on the server
  (`routes/onboarding.py`, meta `onboard:<email>`). People who already have episodes start with it hidden.
- **Sample show (Q4A, Q5A).** One episode in the interface language, in a show of its own marked `sample`; no plan
  counts it (shows, and batch 5 audio hours must skip it); nobody can be invited into it; 重置示例 copies the
  episode's edit files again; it can be deleted and added back from 设置 → 通用. The recording is shared and
  read-only (`<root>/sample/v<N>/<lang>/raw`). Until Leon and Pei record it (Q3), the audio is a placeholder.
- **Collaborators (Q11A)** get the short version: "Sam 邀请你一起剪《X》", review then listen.
- **Name at sign-up (Q12A)**, editable in 账号; older accounts are asked once on 首页.
- **New members need the owner's approval (Q6)** while 「新成员需站长批准」 is on (beta); turning it off at launch
  needs Leon's typed words.
- **Review page version A (E1):** slim list + one card: what was cut, A/B, keep or restore, 剩下的全部保留.
- **本集学到的规则 off the step bar (Q8A)**, reached by a link from 整集试听.
- **Platforms (G2):** export is generic; the show picks its platforms (Apple Podcasts, Spotify, YouTube, 喜马拉雅,
  小宇宙, 其他); 喜马拉雅 tabs only for shows published there. Direct upload is a separate pre-beta batch.
- **Separate tracks (Q9A):** required and said everywhere; the application form asks, mixed-track applicants go
  to the waitlist and are counted.
- **节目资料卡 (C6)** on a new show's 首页: description, names, opener / ending; put away per show.
- Sample music (all verified CC0, John Bartmann, FMA): intro Uptown Fatness, outro Happy African Village, bed
  Safari Time; spares Secret Agent Rock, Afro Sax Freakout. Files still to be downloaded with a license log.
