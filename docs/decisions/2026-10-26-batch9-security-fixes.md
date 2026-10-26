# Batch 9 security fixes (second full scan)

Date: 2026-10-26. Leon picked the recommended option for all five on the batch 9 report page and typed
「按照你推荐的修」 in the thread.

1. Restoring a deleted owner or admin account from the recycle bin (admin site or main site) is the owner's: it brings
   back the role, password and authenticator, which would let one admin re-appoint another.
2. 「退出对方所有登录」 and 「重置两步验证」 also end the person's admin-site sessions (the actor's own stays open).
3. Pictures claiming more than 40 M pixels are refused before decoding (feedback screenshots, show pictures): a small
   PNG could claim 12000×12000 and take ~630 MB to decode.
4. Reset codes: the limits are checked and counted under the lock before the mail goes out, so parallel requests
   can't pass the daily limit or the 60 s pause; a failed send doesn't count.
5. Every email is counted alike (known or not), so the 429 answers no longer tell which emails have accounts. Someone
   who knows an email can still use up its 5 codes a day; that is the cost of a per-email limit and stays.
