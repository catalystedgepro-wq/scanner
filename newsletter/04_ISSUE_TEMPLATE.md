# Catalyst Edge — Single-Issue Template (Prompt 04 output)

One example issue written in full against the W1 theme: "Why every catalyst newsletter lies about its track record." Also the reusable shell for every weekly longform.

---

## Subject Line

**We publish the losses, on purpose**

(6 words, curiosity + stakes, no clickbait, no emoji.)

## Hook (first 2 sentences earn the read)

Every catalyst Discord I've paid for has a pinned thread titled "Wins of the Week." None of them have a pinned thread called "Losses of the Week." That's not an oversight — it's the business model.

## Core Content (under 500 words)

The math: a catalyst service posts 10 picks a week. Three rip. Seven don't. The three get screenshotted, pinned, shared on X. The seven get quietly deleted from the channel by Wednesday. New subscribers see a feed that looks 100% accurate. They pay $99, $199, $499 a month. When their own account goes red, they assume they traded it wrong — not that the pinned wins were selection bias in a crown.

The SEC filing universe is perfect for this scam. EDGAR publishes ~1,400 8-Ks a week. Catalyst services can pick the three that ran after the fact, call it a "next-day alert," and never prove a thing about the selection criteria.

Catalyst Edge is the opposite architecture. Every pick goes into an append-only CSV (`ml_benchmark_log.csv`) with the ticker, the filing type, the model's predicted probability, and the actual outcome 24 hours later. The file grows. Nothing is deleted. Subscribers can download it.

Current audited track record on the hardest list (sec_clean_gappers, 602 filings):
- Hit +2% next session: 44.5%
- Hit +5% intraday: 23.75%
- Average intraday high: 5.12%

That is worse than most paid services *claim*. It is probably better than what most paid services *actually deliver*, because theirs is unaudited.

The LightGBM model shipped yesterday lifts top-decile picks to 50.1% on +2% and 32.1% on +5%, based on 5-fold walk-forward cross-validation. That lift is tiny compared to what Discord screenshots imply. It is real. It compounds.

Day-90 target: 78% / 60% / 15%. If the number at day 90 is not that, I'll print the miss in the subject line of Issue #13 and explain why. That's the deal.

Nothing about this is unique in principle. Hedge funds have audited track records. The Sharpe ratio exists. The reason retail catalyst services don't publish theirs isn't technical. It's that the number would kill the subscription business.

I'm betting the opposite: that one small audience, big enough to matter, will pay for signal with receipts over signal with screenshots.

## Key Takeaway

If your catalyst subscription can't show you its loss rate in one click, you're not paying for edge — you're paying for curated survivorship bias.

## Next Issue Tease

Next week: the 7 SEC filing types that drive 80% of the runs worth trading, and the 200+ that should never appear in your inbox. How to filter EDGAR yourself if you ever need to leave me.

---

## Reusable Shell (for daily briefs and future weeklies)

```
SUBJECT: [specific, ≤ 7 words, curiosity or stake]

HOOK: [2 sentences. Tension or unexpected claim.]

SCOREBOARD: [7-day hit rates vs baseline, pulled from ml_benchmark_log.csv]

CORE:
- Picks table (ticker, catalyst, ml_prob_5pct, entry, invalidation)
- Dilution watch (S-3/424B/ATM on unusual-vol tickers)
- Sympathy ladder (correlated tickers to primary mover)

POST-MORTEM: [yesterday's picks, wins and losses, actual high]

TAKEAWAY: [one sentence, trade-relevant]

TEASE: [specific next-issue hook — not "see you next week"]
```

Every field is filled by script (`build_newsletter_picks.py`) except HOOK and TAKEAWAY, which are the 60-second human layer. Shell is enforced at template level (`newsletter/template.html`) so it cannot drift.
