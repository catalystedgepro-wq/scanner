# Distribution Automaton — Sprint Report 2026-04-26

Three-hour blitz. Pivot from features to distribution. Goal: stand up a meta-tool that ships SEO blog posts on autopilot, queue 5 ICP-targeted posts, ship the first one end-to-end.

## Files added

| Path | Bytes |
|---|---|
| `automaton/distribution/pending_content.yaml` | 4,743 |
| `automaton/distribution/content_smith.py` | 65,877 |
| `automaton/distribution/content_publisher.py` | 8,001 |
| `automaton/distribution/social_rotator.py` | 19,678 |
| `automaton/distribution/conversion_tracker.py` | 6,528 |
| `automaton/distribution/distribution_loop.sh` | 3,489 |
| `docs/blog/free-sec-catalyst-scanner/index.html` | 21,947 |
| `social_inbox/free-sec-catalyst-scanner_x.txt` | 200 |
| `social_inbox/free-sec-catalyst-scanner_linkedin.txt` | 704 |
| `social_inbox/free-sec-catalyst-scanner_reddit.txt` | 1,659 |
| `automaton/distribution/screenshot_free-sec-catalyst-scanner.png` | 299,681 |

Mutated: `docs/blog/index.html` (new card inserted at top of post-list), `docs/sitemap.xml` (new `<url>` entry), crontab.

## Queue state — pending_content.yaml

| # | priority | state | slug | kw |
|---|---|---|---|---|
| 1 | 1 | promoted | free-sec-catalyst-scanner | "free SEC catalyst scanner" |
| 2 | 2 | queued | how-to-trade-8k-filings | "how to trade 8-K filings" |
| 3 | 3 | queued | insider-buying-signal-explained | "insider buying signal" |
| 4 | 4 | queued | short-squeeze-setup-checklist | "short squeeze setup" |
| 5 | 5 | queued | dcf-intrinsic-value-explained | "DCF intrinsic value" |

Each stanza carries: title, h1, target_keyword, secondary_keywords[], cta_target (UTM-tagged to `/preview/?utm_source=blog&utm_campaign=<slug>`), word_count_target, target_search_intent, rationale tied to the ICP. Lower priority fires first; the loop will draft #2 on its next 11:00 UTC fire.

## Live verification — first post

- URL: `https://catalystedgescanner.com/blog/free-sec-catalyst-scanner/`
- HTTP code: **200** (size 22,339 bytes after gzip)
- Blog index: `https://catalystedgescanner.com/blog/` returns 200 with the new card at the top
- Sitemap: `<loc>https://catalystedgescanner.com/blog/free-sec-catalyst-scanner/</loc>` confirmed
- Five `<h2>` sections with anchor IDs `s1..s5` rendering live
- Cinematic hero: gold eyebrow ("FREE SEC CATALYST SCANNER"), cyan title, navy gradient backdrop, dual CTAs ("Get the daily catalyst tape →" / "Open /scanner/")
- Screenshot: `/home/operator/.openclaw/workspace/automaton/distribution/screenshot_free-sec-catalyst-scanner.png` (1440×900, 299KB)

## Cron entry confirmed

```
$ crontab -l | grep distribution
# Distribution Automaton — daily blog draft → publish → social rotate (11:00 UTC)
0 11 * * * bash /home/operator/.openclaw/workspace/automaton/distribution/distribution_loop.sh >> /home/operator/.openclaw/workspace/logs/distribution_loop_cron.log 2>&1
```

Sequence per fire: smith → publisher → rotator → (Mondays only) tracker → optional Discord webhook summary. Lock file at `/tmp/distribution_loop.lock` prevents overlap.

## Blockers found and workarounds

1. **No PyYAML in stdlib.** Worked around with a hand-rolled tolerant YAML reader/writer in `content_smith.py` that round-trips the queue without losing structure. PyYAML used opportunistically when present. Confirmed lossless across two queue mutations.
2. **`utcnow()` deprecation warnings on Python 3.12+.** Cosmetic — pipeline works. Not in scope for this sprint; trivial to swap to `dt.datetime.now(dt.UTC)` later.
3. **`/api/utm-stats` endpoint not yet wired on droplet.** `conversion_tracker.py` falls back to local `data/preview_signups.jsonl`; pageview column reads 0 until that endpoint exists. Leaderboard still ships clean.
4. **X char budget.** Initial copy hit 282 chars (over 280). Tuned the `free-sec-catalyst-scanner` X stanza to 200 chars including the URL. Other slugs already fit.
5. **No GROQ_API_KEY.** All five post-body templates ship with hand-authored heuristic content (real shape on day one). Each `<h2>` section carries a `<!-- TODO: LLM-FILL -->` marker so the eventual upgrade pass can rewrite in voice without re-architecting.

## Next-action punch list (operator)

1. **Set `GROQ_API_KEY`** in the workspace env so future drafts get LLM-rewritten body sections (template stays static; only paragraph copy is upgraded).
2. **Wire `/api/utm-stats` endpoint on cerebro droplet** that exposes pageviews per `utm_campaign`, then `conversion_tracker.py` will populate the `PV` column without code changes — write to `data/blog_traffic.jsonl`, one record per pageview.
3. **Wire `data/preview_signups.jsonl`** — append on each Stripe / preview-form submit, shape `{"ts","email","utm_source","utm_campaign","ip","ua"}`. Tracker reads it as-is.
4. **Set `DISCORD_WEBHOOK_URL`** in the cron env so phase 5 posts the summary channel ping. Not blocking; loop runs without it.
5. **Confirm next 11:00 UTC fire** drafts `how-to-trade-8k-filings`, publishes it, and writes 3 social_inbox files. Tail `logs/distribution_loop_cron.log` and `logs/distribution_loop.log` after the first overnight fire.
6. **Manual review of 4 remaining posts before they auto-publish**: each post body is hand-authored and ships verbatim until LLM-fill is wired. If anything in the static templates needs voicing, edit the `_body_*` functions in `content_smith.py` before the next fire.
7. **Add a v0 `og/blog-<slug>.png` per post** for higher CTR on X/LinkedIn previews. Currently all posts share the generic `/press/logo.png` open-graph image.
