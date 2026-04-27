# Catalyst Edge — Distribution Playbook
**Created:** 2026-04-13 | **Baseline:** 5 GA users, 9 Beehiiv subs, $0 revenue

---

## Target Audience Distribution Map

### Reddit (Highest ROI for free organic)

| Subreddit | Members | Content Angle | Post Frequency |
|-----------|---------|---------------|----------------|
| r/pennystocks | 2M+ | Pre-market gap plays from SEC filings, squeeze radar | 2x/week (Tue/Fri) |
| r/Daytrading | 800K+ | Scanner methodology, how-to-trade-8K posts | 2x/week (Mon/Wed) |
| r/stocks | 7M+ | Weekly catalyst recap, convergence alerts | 1x/week (Sat) |
| r/wallstreetbets | 16M+ | Only when a pick hits 40%+ (proof posts) | Opportunistic |
| r/RobinhoodPennyStocks | 300K+ | Simple picks with price targets | 1x/week (Thu) |
| r/options | 1M+ | Options flow + SEC convergence signals | 1x/week |
| r/StockMarket | 3M+ | Educational: how catalyst scoring works | 1x/week |
| r/CatalystEdgePro | OWN | Daily picks, scanner screenshots, community | Daily |

**Rule:** 90/10 — 90% value (analysis, education, discussion), 10% self-reference. Never hard-sell.

### X/Twitter (Fastest feedback loop)

**Daily routine (7-8:30 AM ET):**
1. Hook tweet with bold claim backed by data
2. 3-5 ticker thread with catalyst chain explanation
3. Scanner screenshot showing convergence
4. CTA: "Free daily picks → [newsletter link]"

**Accounts to engage with (10K-100K followers):**
- SEC filing / catalyst accounts
- Pre-market gap scanners
- Options flow traders
- Momentum traders
- Small-cap researchers

**Engagement strategy:**
- 5-10 genuine, value-adding replies per day
- Quote-tweet with analysis when someone mentions a ticker you scanned
- Weekly "Catalyst Edge Scoreboard" showing pick outcomes

### Discord (Community + retention)

**Own server channels:**
- #daily-picks (automated webhook from pipeline)
- #scanner-alerts (convergence + squeeze alerts)
- #pre-market-brief (4:30 AM ET daily)
- #general (community discussion)
- #premium (Edge Pro subscribers only)

**Cross-promotion targets:**
- Bear Bull Traders (free tier)
- MarketHQ Free Discord
- Stock Market Chat
- Momentum Alert Hub

### YouTube (Long-term SEO + authority)

**Content calendar:**
- Daily: 60-second Short — "Today's Top 3 Catalyst Picks" (automated via generate_tiktok_video.py)
- Weekly: 5-10 min walkthrough — "How I Found [TICKER] Before It Moved 40%"
- Monthly: 15-min deep dive — "Scanner Methodology" or "How to Read SEC Filings"

**Channel optimization:**
- Pin scanner demo as channel trailer
- End screen → newsletter signup
- Description → scanner link + pricing link

### TikTok + Instagram Reels (Awareness)

- Same 60-second content as YouTube Shorts
- Captions: bold text overlays with ticker + catalyst
- Bio link → newsletter signup (Linktree or direct)

### LinkedIn (Professional credibility)

- 2-3 posts/week: market insights, methodology, "how we built this"
- Target: RIA firms, quant traders, fintech professionals
- Tone: professional, data-driven, no hype

### Beehiiv Newsletter (Conversion engine)

- **Free tier:** Daily picks + catalyst summary (what you have now)
- **Reader tier ($12/mo):** Full scanner access, AI queries, archive
- **Growth tactics:**
  - Referral milestones: 1 ref→watchlist, 3→priority alerts, 5→1mo AI free, 10→founding badge
  - Cross-promote in every social post
  - Ad Network: Upgrade to Scale plan → claim 1440 Media ($1.31/click)

---

## Week 1 Priority Actions (This Week)

### User must do (manual, one-time):
1. [ ] Run `bash ~/.openclaw/workspace/setup_social_profiles.sh` for Reddit, LinkedIn, Instagram, TikTok, YouTube
2. [ ] Create Ko-fi account at ko-fi.com, connect Stripe
3. [ ] Create Discord server, generate webhook URL, share it
4. [ ] Create r/CatalystEdgePro subreddit
5. [ ] Enable Beehiiv premium: Reader tier at $12/mo and $99/yr
6. [ ] Submit sitemap in Google Search Console (instructions below)

### Automated (already done or in progress):
- [x] Pricing page live at /pricing/
- [x] Ko-fi CTAs added to Cerebro explainer
- [x] Sitemap expanded (7+ URLs, auto-discovers glossary pages)
- [x] Deploy script updated for /pricing/ and /glossary/ routes
- [x] Nginx routes configured for pricing and glossary
- [x] Reddit posting script (post_to_reddit.cjs)
- [x] LinkedIn posting script (post_to_linkedin.cjs)
- [x] Social orchestrator (run_social_posts.sh) with all 7 platforms
- [ ] SEO glossary pages (5 pages, building now)
- [ ] Video script refresh (in progress)

---

## Google Search Console Setup

1. Go to https://search.google.com/search-console
2. Add property: `https://catalystedgescanner.com`
3. Verify via HTML file upload or DNS TXT record
4. Go to Sitemaps → Add: `https://catalystedgescanner.com/sitemap.xml`
5. Request indexing for key pages:
   - https://catalystedgescanner.com/
   - https://catalystedgescanner.com/scanner/
   - https://catalystedgescanner.com/cerebro/
   - https://catalystedgescanner.com/pricing/
   - https://catalystedgescanner.com/methodology/

---

## Competitor Landscape (SEC Filing Tools)

| Tool | Price | What They Do | Our Advantage |
|------|-------|-------------|---------------|
| Benzinga Pro | $37-197/mo | Real-time news, calendar | We scan SEC filings automatically before news breaks |
| Trade Ideas | $89-178/mo | AI scanner (Holly) | We combine SEC + options + short interest convergence |
| Finviz | $39.50/mo | Static 2D screener | We render 15K+ tickers in 3D with live data |
| Hudson Labs | Enterprise | AI red flag detection | We score catalysts, not just flag risk |
| Footnoted | Free blog | Manual filing highlights | We automate and score systematically |
| Unusual Whales | $48/mo | Options flow | We show WHY flow is happening (the filing behind it) |
| Quiver Quant | $25-75/mo | Alt data, congress | We combine their signals with more (SEC + momentum + squeeze) |

---

## Revenue Milestones

| Milestone | When | Revenue |
|-----------|------|---------|
| Ko-fi tips start | Week 1 | $50-200/mo |
| Beehiiv Reader tier (50 subs) | Month 1-2 | $600/mo |
| Edge Pro tier (20 subs) | Month 2-3 | $780/mo |
| 1,000 newsletter subs | Month 3-4 | Beehiiv Ad Network eligible |
| Edge API (5 subs) | Month 4-6 | $495/mo |
