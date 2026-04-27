# Catalyst Edge — 3-Email Welcome Sequence (Prompt 02 output)

Sent from Beehiiv automation. Email 1 fires on confirm-subscribe. Email 2 at T+24h. Email 3 at T+72h.

---

## Email 1 — VALUE (sent immediately)

**Subject:** Your first three picks are below

Welcome. No story yet. Value first.

Here are the three SEC catalyst plays our model ranked highest this morning, with the probability the stock hits +5% intraday and the one reason each:

| Ticker | ml_prob_5pct | Catalyst | Why the model likes it |
|---|---|---|---|
| {{TICKER_1}} | {{P1}} | {{FORM_1}} | {{REASON_1}} |
| {{TICKER_2}} | {{P2}} | {{FORM_2}} | {{REASON_2}} |
| {{TICKER_3}} | {{P3}} | {{FORM_3}} | {{REASON_3}} |

**Scoreboard, last 7 days:** hit +2% {{HIT2}}% · hit +5% {{HIT5}}% · avg intraday high {{AVGRUN}}%.

Baseline (no model, just the filing type): 44.5 / 23.8 / 5.1. If the numbers above are worse than the baseline, the model is off that week and the issue will say so.

That's it. Trade your own book. Tomorrow 7:30 AM ET you get the next list + the post-mortem on today's losers.

---

## Email 2 — STORY (T+24h)

**Subject:** I lost $4,200 on one S-3

Two years ago I held a small-cap overnight through a catalyst I'd bet on all day. At 7:58 AM ET an S-3 shelf offering hit the tape. Premarket cut 28%. I didn't know what an S-3 was. The Discord I was paying $99/mo didn't mention it. They posted the winners from the same day. My S-3 ticker was deleted from the pinned thread by Wednesday.

That's when I started reading EDGAR directly. Then scraping it. Then scoring every filing type against next-session outcomes. 8,445 rows of historical catalyst outcomes later, there's a model.

I'm writing this newsletter because if you trade catalysts and you don't have a filing-level audit trail, you're Marcus two years ago. I was Marcus two years ago.

The model isn't magic. Baseline is 44.5 / 23.75 / 5.1. Current walk-forward lift is +6.8 pts on +2% and +9.8 pts on +5% top-decile. Day-90 target is 78 / 60 / 15. Every week that number moves in `ml_benchmark_log.csv`, published in issue footer.

Tomorrow: what you actually get and how often.

---

## Email 3 — EXPECTATIONS (T+72h)

**Subject:** Here's exactly what shows up

**Send time:** 7:30 AM ET, Monday–Friday. Never 6 AM, never 9:15. Consistent with pre-market prep window.

**Each issue contains, in order:**
1. Scoreboard — trailing 7-day hit rates vs baseline, linked to the raw CSV.
2. Top 3 picks — ticker, catalyst type, ml_prob_5pct, entry level, invalidation.
3. Dilution watch — any S-3 / 424B / ATM on tickers with unusual volume.
4. Sympathy ladder — if yesterday had a primary mover, the correlated tickers ranked by historical sympathy coefficient.
5. Yesterday's post-mortem — every pick from the prior issue, win or loss, with the number that moved.

**What you will not get:** sponsored picks, affiliate links to brokers, emoji-stacked hype tweets reformatted, or daily market commentary that could have been written about any day.

**Frequency:** 5 issues per week. No weekend issues unless a halted/resumed ticker warrants a Sunday alert — and that's flagged in the subject line as `[ALERT]`.

**Paid ($9/mo, Stripe):** the same issue + Cerebro HUD live view with entity map, sympathy correlation graph, and real-time SEC filing stream. Free tier keeps picks + scoreboard forever. Paid is for the traders who want the machinery, not just the output.

Reply to this email with the ticker type you care most about (biotech 8-Ks, reverse mergers, gappers, dilution). It trains me which column to expand.

See you at 7:30 AM.
