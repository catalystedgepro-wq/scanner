#!/usr/bin/env python3
"""generate_glossary_pages.py — Batch-generate SEO glossary pages for Catalyst Edge.

Each page targets a long-tail keyword traders search for, includes:
- Proper <title>, meta description, canonical URL
- JSON-LD FAQPage schema for rich snippets
- Internal links to scanner, other glossary pages
- Subscribe CTA
- Consistent design matching existing glossary pages

Run after generate_seo_site.py to add pages, then redeploy.
"""
from __future__ import annotations

import html as html_mod
import json
import os
from pathlib import Path

ROOT = Path(__file__).parent
DOCS = ROOT / "docs"
GLOSSARY_DIR = DOCS / "glossary"
GLOSSARY_DIR.mkdir(parents=True, exist_ok=True)

SITE = "https://catalystedgescanner.com"
AGENCY = "https://catalystedge.agency"

# ── Page definitions ───────────────────────────────────────────────────────

PAGES: list[dict] = [
    {
        "slug": "what-is-form-4",
        "title": "What is SEC Form 4? Insider Trading Signals Explained | Catalyst Edge",
        "description": "Learn how SEC Form 4 reveals insider buying and selling, why it matters for traders, and how Catalyst Edge tracks insider transactions to find high-conviction setups.",
        "h1": "What is SEC Form 4?",
        "subtitle": "Insider Trading Signals Every Trader Should Watch",
        "sections": [
            ("What is a Form 4 filing?",
             "SEC Form 4 is filed whenever a company insider (director, officer, or 10%+ shareholder) buys or sells shares. These filings must be submitted within 2 business days of the transaction, making them one of the fastest public signals of insider sentiment. When a CEO buys $500K of their own stock on the open market, that's a Form 4."),
            ("Why traders watch Form 4 filings",
             "Insiders know their company better than any analyst. When multiple insiders buy simultaneously (a 'cluster buy'), it often precedes positive catalysts like earnings beats, FDA approvals, or M&A announcements. Academic research shows insider purchases outperform the market by 7-10% annually. Catalyst Edge scans every Form 4 filed with EDGAR and flags cluster buys automatically."),
            ("How to read a Form 4",
             "The key fields are: Transaction Code (P = purchase, S = sale, A = award), shares transacted, price per share, and shares owned after the transaction. Open-market purchases (Code P) carry the strongest signal because insiders are spending their own money. Derivative transactions (options exercises) are less meaningful."),
            ("Form 4 vs Form 3 vs Form 5",
             "Form 3 is the initial ownership report when someone becomes an insider. Form 4 reports changes in ownership. Form 5 is an annual summary of transactions that should have been reported on Form 4 but were exempt. For traders, Form 4 is the one that matters — it shows real-time insider activity."),
        ],
        "faqs": [
            ("How quickly do Form 4 filings appear on EDGAR?", "Form 4 filings must be submitted within 2 business days of the transaction. Most appear on EDGAR within hours. Catalyst Edge checks EDGAR every 15 minutes during market hours."),
            ("Is insider buying always bullish?", "Not always, but statistically it's a strong signal. Insider purchases outperform the market by 7-10% per year on average. The strongest signals come from cluster buys (multiple insiders buying within days) and large purchases relative to the insider's compensation."),
            ("What is a Form 4 cluster buy?", "A cluster buy occurs when 3 or more insiders at the same company file Form 4 purchase reports within a 14-day window. Catalyst Edge automatically detects and flags these patterns."),
        ],
    },
    {
        "slug": "what-is-sc-13d",
        "title": "What is Schedule 13D? Activist Investor Filing Guide | Catalyst Edge",
        "description": "Understand SEC Schedule 13D filings, how activist investors use them, and why they create trading opportunities. Catalyst Edge scans 13D filings daily.",
        "h1": "What is Schedule 13D?",
        "subtitle": "How Activist Investor Filings Create Trading Catalysts",
        "sections": [
            ("What is a Schedule 13D filing?",
             "Schedule 13D is filed when an investor or group acquires more than 5% of a company's voting shares with the intent to influence management. Unlike the passive 13G filing, a 13D signals activist intentions — the investor plans to push for changes like board seats, asset sales, mergers, or strategic pivots."),
            ("Why 13D filings move stocks",
             "When an activist like Carl Icahn, Elliott Management, or Starboard Value files a 13D, the stock typically jumps 5-15% in the first week. The market prices in the expectation that the activist will unlock value through operational improvements, capital returns, or a sale of the company. Catalyst Edge flags new 13D filings within minutes of their EDGAR submission."),
            ("13D vs 13G: the critical difference",
             "Schedule 13G is the passive version — filed by institutional investors who hold 5%+ but have no activist agenda (mutual funds, index funds). A 13D means the investor explicitly intends to influence the company. When a holder converts from 13G to 13D, it signals a shift from passive to activist — one of the strongest catalysts in the market."),
            ("How to trade 13D filings",
             "The initial pop on a 13D filing is just the beginning. The real value unfolds over weeks as the activist's demands become public. Watch for proxy fights, board nominations, and strategic review announcements. Catalyst Edge tracks the full lifecycle from initial filing through resolution."),
        ],
        "faqs": [
            ("How soon does a stock react to a 13D filing?", "Most of the initial move happens within 24-48 hours of the filing appearing on EDGAR. Catalyst Edge detects new 13D filings during each scan cycle and sends convergence alerts when combined with other bullish signals."),
            ("What is a 13D/A amendment?", "A 13D/A is an amendment to an existing 13D filing. Amendments report changes in ownership percentage, investment intent, or proposed actions. A 13D/A showing increased ownership is bullish — the activist is doubling down."),
        ],
    },
    {
        "slug": "what-is-gap-up-stock",
        "title": "What is a Gap Up? How to Find Gap Stocks Before Market Open | Catalyst Edge",
        "description": "Learn what gap-up stocks are, why they happen, and how SEC filing scanners find gap candidates before the market opens. Free daily gap scanner from Catalyst Edge.",
        "h1": "What is a Gap Up Stock?",
        "subtitle": "Finding Pre-Market Gaps Before the Crowd",
        "sections": [
            ("What is a gap up?",
             "A gap up occurs when a stock opens significantly higher than its previous closing price, creating a visible 'gap' on the chart. Gaps happen because of overnight news — earnings reports, FDA decisions, merger announcements, or SEC filings — that shift the stock's value before regular trading begins."),
            ("Types of gaps traders watch",
             "Breakaway gaps occur at the start of a new trend and often hold. Continuation gaps happen mid-trend and signal strong momentum. Exhaustion gaps appear at the end of a move and frequently fill. For SEC catalyst traders, the most profitable are breakaway gaps triggered by material filings (8-K events, insider cluster buys, activist 13D filings)."),
            ("How Catalyst Edge finds gap candidates",
             "Most traders scan for gaps after the market opens — by then, the easy money is gone. Catalyst Edge scans SEC EDGAR filings overnight and scores each ticker based on filing type, insider activity, price momentum, and sector rotation signals. The daily scanner publishes results before 8 AM ET, giving subscribers a head start on gap identification."),
            ("Gap trading strategies",
             "Gap and Go: Buy the gap if volume confirms and the catalyst is strong (8-K material event, insider cluster buy). Gap Fill: Short if the gap was caused by a weak catalyst (routine filing, small insider sale) and the stock shows exhaustion at the open. Fade the Gap: Wait for the initial euphoria to fade, then enter on the pullback to the gap level."),
        ],
        "faqs": [
            ("What causes stocks to gap up?", "The most common catalysts are earnings surprises, FDA approvals, merger announcements, activist investor filings (13D), insider buying clusters (Form 4), and favorable analyst upgrades. SEC filings often contain these catalysts before they hit mainstream news."),
            ("How do I find gap stocks before the market opens?", "Use an SEC filing scanner like Catalyst Edge that monitors EDGAR overnight. The scanner identifies material filings, scores them for gap potential, and publishes a watchlist before the pre-market session."),
            ("Do gap stocks always keep going up?", "No. Studies show about 60-70% of gaps eventually fill (the stock returns to the pre-gap price). The key is distinguishing between strong catalysts (material 8-K, activist 13D) that sustain momentum and weak catalysts that produce exhaustion gaps."),
        ],
    },
    {
        "slug": "sec-filing-types-for-traders",
        "title": "SEC Filing Types Every Trader Should Know | Complete Guide | Catalyst Edge",
        "description": "Complete guide to SEC filing types that move stocks: 8-K, Form 4, 13D, S-3, 6-K, and more. Learn which filings create the best trading catalysts.",
        "h1": "SEC Filing Types for Traders",
        "subtitle": "Which Filings Move Stocks and Why",
        "sections": [
            ("The filings that matter",
             "Not all SEC filings are created equal. Out of 60+ filing types on EDGAR, only about 8-10 consistently create trading opportunities. The most actionable: 8-K (material events), Form 4 (insider transactions), SC 13D (activist positions), S-3 (shelf registrations), and 6-K (foreign issuer disclosures)."),
            ("8-K: Material Event Filings",
             "The 8-K is the most important filing for catalyst traders. Companies must file an 8-K within 4 business days of any 'material event' — earnings surprises, mergers, executive changes, bankruptcy, going-concern warnings, and more. Item numbers tell you the type: Item 1.01 (material agreement), Item 2.02 (earnings), Item 5.02 (executive departure), Item 8.01 (other events)."),
            ("Form 4: Insider Transactions",
             "Filed within 2 business days of any insider buy or sell. Open-market purchases (Transaction Code P) are the strongest bullish signal. Cluster buys (3+ insiders buying within 14 days) have historically preceded positive catalysts. Catalyst Edge auto-detects cluster buy patterns."),
            ("SC 13D/13G: Large Holder Reports",
             "Filed when an entity acquires 5%+ of a company's shares. 13D = activist intent (bullish catalyst). 13G = passive holding (informational only). A switch from 13G to 13D signals an activist campaign — historically one of the strongest catalysts."),
            ("S-3 and 424B: Shelf Registrations",
             "An S-3 allows a company to sell securities 'off the shelf' without filing a new registration each time. While often seen as dilutive (bearish), smart money watches for S-3 filings paired with insider buying — this combination often precedes a positive catalyst where the company needs to raise capital for growth, not survival."),
            ("6-K: Foreign Issuer Reports",
             "The international equivalent of an 8-K. Filed by foreign private issuers (ADRs). Important for biotech traders since many clinical-stage pharma companies are foreign issuers. 6-K filings containing clinical trial results can move stocks 20-50%."),
        ],
        "faqs": [
            ("Which SEC filing moves stocks the most?", "8-K filings cause the largest and most frequent price moves because they report material events (mergers, earnings, FDA decisions). Form 4 cluster buys are the most reliable predictor of sustained price appreciation."),
            ("How quickly can I see new SEC filings?", "Filings appear on EDGAR within minutes of submission. Catalyst Edge checks EDGAR every 15 minutes during market hours and provides pre-market scans of overnight filings before 8 AM ET."),
            ("Are all SEC filings public?", "Yes. All filings submitted to EDGAR are publicly available at sec.gov/cgi-bin/browse-edgar. Catalyst Edge automates this process by scanning, scoring, and ranking filings so you don't have to read thousands of documents manually."),
        ],
    },
    {
        "slug": "what-is-lockup-expiration",
        "title": "What is IPO Lockup Expiration? Trading the Unlock | Catalyst Edge",
        "description": "Learn how IPO lockup expirations create trading opportunities, when insiders can sell, and how to position ahead of lockup dates with Catalyst Edge.",
        "h1": "What is IPO Lockup Expiration?",
        "subtitle": "Trading the Insider Unlock Window",
        "sections": [
            ("What is a lockup period?",
             "After an IPO, insiders (founders, executives, early investors) are restricted from selling their shares for a set period — typically 90-180 days. This 'lockup period' prevents a flood of insider selling from crashing the stock immediately after the IPO. When the lockup expires, insiders can finally sell."),
            ("Why lockup expirations move stocks",
             "When the lockup expires, the number of shares available for trading can increase by 3-10x overnight. Even if insiders don't sell immediately, the market anticipates selling pressure and often prices it in 1-2 weeks before the expiration date. Stocks typically drop 1-3% around lockup expiration, but the setup is more nuanced than 'just short it.'"),
            ("How to trade lockup expirations",
             "The contrarian play: if a stock drops 5-10% into a lockup expiration but insiders file Form 4s showing they're NOT selling, the relief bounce can be significant. Catalyst Edge cross-references lockup dates with Form 4 filings to identify these 'lockup + hold' setups. When insiders buy during their first opportunity to sell, it's one of the strongest bullish signals in the market."),
            ("Finding lockup dates",
             "Lockup terms are disclosed in the S-1 filing (IPO prospectus). Catalyst Edge parses S-1 filings to extract lockup dates and tracks them on a rolling calendar. The scanner alerts you when lockup expirations are approaching and cross-references with insider transaction data."),
        ],
        "faqs": [
            ("How long is a typical IPO lockup?", "Most lockups are 180 days (6 months), but they can range from 90 to 365 days. Some IPOs have staggered lockups where different insider groups can sell at different times."),
            ("Do stocks always drop at lockup expiration?", "Not always. On average, stocks decline 1-3% around lockup expiration, but if insiders choose to hold (or buy more), the stock often rallies on the positive signal."),
        ],
    },
    {
        "slug": "premarket-gap-scanner",
        "title": "Free Pre-Market Gap Scanner | SEC Filing Analysis | Catalyst Edge",
        "description": "Free daily pre-market gap scanner powered by SEC filing analysis. Catalyst Edge scans 300+ EDGAR filings overnight to find gap-up candidates before 8 AM ET.",
        "h1": "Pre-Market Gap Scanner",
        "subtitle": "SEC-Powered Gap Detection Before the Bell",
        "sections": [
            ("What is a pre-market gap scanner?",
             "A pre-market gap scanner identifies stocks likely to open significantly higher or lower than yesterday's close. Traditional scanners use price-based screens (volume spikes, pre-market movers). Catalyst Edge takes a different approach: scanning SEC EDGAR filings overnight to find the catalysts that cause gaps before they show up on price screens."),
            ("How the Catalyst Edge scanner works",
             "Every morning, the scanner: (1) Pulls 300+ new SEC filings from EDGAR, (2) Classifies each by catalyst type (8-K event, insider buy, activist filing), (3) Scores tickers using a multi-factor model (filing type, historical gap rate, sector momentum, insider activity), (4) Publishes a ranked watchlist before 8 AM ET with the top picks for the day."),
            ("Scanner categories",
             "Gappers: High-probability gap-up candidates based on material filings + price momentum. Value Plays: Undervalued tickers with positive filing catalysts (insider buying at lows). Moat Builders: Companies with structural advantages (patent filings, recurring revenue, debt reduction) showing through their SEC filings."),
            ("Why SEC filings beat price scanners",
             "Price scanners show you what already happened. Filing scanners show you why it's about to happen. By the time a stock shows up on a pre-market mover list, the gap is already priced in. Catalyst Edge finds the filing first, letting you position before the gap appears on price screens."),
        ],
        "faqs": [
            ("Is the Catalyst Edge scanner free?", "Yes. The daily scanner page is free and publishes results every trading day before 8 AM ET. Premium features (real-time alerts, Cerebro 3D HUD, convergence signals) require a Pro subscription."),
            ("What time does the scanner update?", "The main scan runs at 4:05 AM ET (Monday-Friday). Intraday updates run at 2:00 PM ET. EOD recaps run hourly from 3-8 PM ET."),
            ("How accurate is the gap scanner?", "The scanner tracks its own performance. Historical win rates and post-scan price action are published on the scanner page so you can evaluate accuracy transparently."),
        ],
    },
    {
        "slug": "insider-buying-signals",
        "title": "Insider Buying Signals: How to Spot Smart Money Moves | Catalyst Edge",
        "description": "Learn how to identify meaningful insider buying patterns from SEC Form 4 filings. Cluster buys, CEO purchases, and insider signals that predict stock moves.",
        "h1": "Insider Buying Signals",
        "subtitle": "Following Smart Money Through SEC Filings",
        "sections": [
            ("Why insider buying matters",
             "Corporate insiders — CEOs, CFOs, directors, and large shareholders — have the deepest understanding of their company's prospects. When they buy shares on the open market with their own money, they're putting real capital behind their conviction. Academic studies consistently show that insider purchases outperform the market by 7-10% annually."),
            ("The strongest insider signals",
             "Not all insider buying is equal. The strongest signals: (1) Cluster buys — 3+ insiders buying within 14 days, (2) CEO/CFO purchases — C-suite has the best visibility, (3) Large purchases relative to compensation — meaningful skin in the game, (4) Buying during price weakness — insiders buying dips shows conviction, (5) First-time buyers — insiders who never bought before suddenly acquiring shares."),
            ("Insider buying vs insider selling",
             "Insider selling is far less informative. Insiders sell for many reasons: diversification, taxes, personal expenses, pre-planned 10b5-1 sales. But insiders buy for only one reason: they believe the stock is going up. This asymmetry makes insider buying a more reliable signal than insider selling."),
            ("How Catalyst Edge tracks insiders",
             "The scanner processes every Form 4 filed with EDGAR, extracts transaction details, and runs cluster detection algorithms. When a cluster buy pattern is detected (3+ insiders, 14-day window, open-market purchases), it triggers a convergence alert and boosts the ticker's score in the daily ranking."),
        ],
        "faqs": [
            ("What is a Form 4 cluster buy?", "A cluster buy is when 3 or more insiders at the same company file Form 4 purchase reports within a 14-day window. This pattern historically precedes positive catalysts and outperforms single insider purchases."),
            ("Where can I find insider buying data?", "All insider transactions are filed as Form 4 on SEC EDGAR (sec.gov). Catalyst Edge automates this by scanning every Form 4, detecting patterns, and ranking tickers by insider activity alongside other catalyst signals."),
            ("Do insiders always beat the market?", "On average, yes — insider purchases outperform by 7-10% per year. But individual insider buys can still lose money. The strongest signal comes from cluster buys combined with other catalysts (8-K events, sector momentum), which is what Catalyst Edge's convergence scoring measures."),
        ],
    },
    {
        "slug": "what-is-sympathy-play",
        "title": "What is a Sympathy Play? Trading Sector Momentum | Catalyst Edge",
        "description": "Learn how sympathy plays work in trading, how one stock's catalyst can move an entire sector, and how to identify sympathy chain opportunities.",
        "h1": "What is a Sympathy Play?",
        "subtitle": "How One Catalyst Moves an Entire Sector",
        "sections": [
            ("Understanding sympathy plays",
             "A sympathy play occurs when a stock moves in the same direction as a related stock that just had a catalyst event. If a biotech company gets FDA approval for a cancer drug, other biotech companies working on similar treatments often rally in sympathy — even without their own news. This 'sympathy chain' effect creates some of the most profitable intraday trading setups."),
            ("Why sympathy plays happen",
             "Sympathy moves happen because traders extrapolate catalysts to peers. An FDA approval for Drug X validates the science behind similar drugs. A big oil company beating earnings suggests the whole energy sector is strong. Algorithmic traders and sector-rotation funds amplify these moves by automatically buying correlated stocks."),
            ("How to identify sympathy chains",
             "Step 1: Identify the lead stock (the one with the actual catalyst). Step 2: Find peers in the same sub-sector or with similar products. Step 3: Check if peers are lagging the lead stock's move. Step 4: Enter the sympathy play before the rotation reaches it. Catalyst Edge tracks sympathy chains automatically using GICS sector classification and correlation analysis."),
            ("Sympathy play risks",
             "Sympathy plays fade faster than catalyst-driven moves. The further a stock is from the lead catalyst, the weaker and shorter the sympathy move. Always use tight stops on sympathy plays and take profits quickly — these are momentum trades, not investments."),
        ],
        "faqs": [
            ("How long do sympathy plays last?", "Most sympathy moves last 1-3 days. First-order sympathy (direct competitors) can sustain for a week. Second-order sympathy (same sector, different product) typically fades within 24 hours."),
            ("Can Catalyst Edge identify sympathy chains?", "Yes. The scanner uses GICS sector classification and correlation analysis to map sympathy relationships. When a lead stock triggers a catalyst alert, the system identifies and ranks potential sympathy plays in the same sector."),
        ],
    },
    {
        "slug": "what-is-deep-value-investing",
        "title": "What is Deep Value Investing? Finding Undervalued Stocks | Catalyst Edge",
        "description": "Learn deep value investing strategy, how to find undervalued stocks using SEC filings, and how Catalyst Edge screens for deep value opportunities daily.",
        "h1": "What is Deep Value Investing?",
        "subtitle": "Finding Diamonds in the SEC Filing Rough",
        "sections": [
            ("Deep value investing explained",
             "Deep value investing means buying stocks trading significantly below their intrinsic value — often at less than book value, liquidation value, or replacement cost. Unlike traditional value investing (buying good companies at fair prices), deep value targets beaten-down, unloved, or misunderstood companies where the market has overcorrected."),
            ("The SEC filing edge",
             "SEC filings reveal deep value that price screens miss. A company might look terrible on a stock screener but its 10-K shows net cash exceeding market cap. An 8-K might disclose a strategic review or asset sale that could unlock hidden value. Insider buying at multi-year lows (Form 4) signals that management sees value the market doesn't. Catalyst Edge combines price metrics with filing intelligence to find these setups."),
            ("Deep value screening criteria",
             "The Catalyst Edge deep value screen looks for: Price-to-Book under 1.0 (trading below asset value), insider buying at lows (Form 4 cluster buys), net cash positions (cash exceeds total debt), activist involvement (13D filings), and catalyst triggers (8-K events that could unlock value). Tickers that score on 3+ criteria earn the highest deep value grades."),
            ("Risks of deep value",
             "Deep value stocks are cheap for a reason. Value traps — stocks that are cheap and keep getting cheaper — are the primary risk. The SEC filing overlay helps mitigate this: insider buying signals management confidence, 13D filings signal external pressure for change, and 8-K events can be the catalyst that finally unlocks value."),
        ],
        "faqs": [
            ("What is a value trap?", "A value trap is a stock that appears cheap on valuation metrics but continues to decline because the underlying business is deteriorating. The key to avoiding value traps is looking for catalysts (insider buying, activist involvement) that can reverse the decline."),
            ("How does deep value differ from regular value investing?", "Regular value investing buys quality companies at fair prices (Buffett-style). Deep value buys distressed or unloved companies at steep discounts, betting on mean reversion or a specific catalyst. The returns are higher but so is the risk."),
        ],
    },
    {
        "slug": "how-to-read-sec-filings",
        "title": "How to Read SEC Filings: A Trader's Guide | Catalyst Edge",
        "description": "Step-by-step guide to reading SEC filings for trading. Learn which sections matter, what to look for, and how to extract actionable trading signals.",
        "h1": "How to Read SEC Filings",
        "subtitle": "Extracting Trading Signals from EDGAR",
        "sections": [
            ("Why traders should read filings",
             "Most retail traders rely on news headlines and social media for stock ideas. By the time a catalyst hits CNBC, the move is largely over. SEC filings are the primary source — companies are legally required to disclose material events within days. Learning to read filings gives you a structural edge over traders who wait for the media to interpret them."),
            ("The 80/20 of reading filings",
             "You don't need to read entire filings. For 8-K filings, focus on Items 1.01 (material agreements), 2.02 (financial results), and 8.01 (other events). For Form 4, look at Transaction Code (P=purchase), shares transacted, and whether it's part of a cluster. For 13D, read the 'Purpose of Transaction' section — this tells you exactly what the activist plans to do."),
            ("Speed-reading techniques",
             "Start with the filing header: form type, company name, date. Ctrl+F for keywords: 'merger', 'acquisition', 'FDA', 'approval', 'guidance', 'raise', 'beat', 'miss', 'bankruptcy', 'going concern'. Check the filing date vs the event date — old news repriced is less actionable than breaking catalysts. Catalyst Edge automates this entire process, but knowing how to verify signals manually makes you a better trader."),
            ("Common traps in SEC filings",
             "Not all filings are bullish. Watch for: dilutive offerings (S-3 + prospectus supplement = stock sale), going-concern warnings in 10-K filings, insider sales disguised as 'estate planning' (still net selling), and 8-K Item 4.02 (auditor dismissal — major red flag). Catalyst Edge's scoring model accounts for these negative signals and adjusts rankings accordingly."),
        ],
        "faqs": [
            ("Where do I find SEC filings?", "All public company filings are available free at sec.gov/cgi-bin/browse-edgar. You can search by company name, ticker, or CIK number. Catalyst Edge automates this by scanning EDGAR continuously and surfacing the most actionable filings."),
            ("How long does it take to read an SEC filing?", "A skilled trader can scan an 8-K in 2-3 minutes by focusing on item numbers and keywords. Form 4 filings take about 30 seconds. 10-K annual reports can take hours — but for trading purposes, you only need the risk factors and management discussion sections."),
            ("Can AI read SEC filings?", "Yes. Catalyst Edge uses NLP (natural language processing) to extract sentiment and key events from filing text. The system identifies positive catalysts (merger agreements, earnings beats, insider purchases) and negative signals (going-concern warnings, dilutive offerings) automatically."),
        ],
    },
    {
        "slug": "free-stock-scanner",
        "title": "Free Stock Scanner | SEC Filing-Powered Daily Scans | Catalyst Edge",
        "description": "Free daily stock scanner powered by SEC EDGAR filings. Scans 300+ filings overnight, scores tickers for gap potential, and publishes a watchlist before market open.",
        "h1": "Free Stock Scanner",
        "subtitle": "SEC-Powered Daily Analysis, Zero Cost",
        "sections": [
            ("What makes this scanner different",
             "Most free stock scanners use lagging indicators — yesterday's volume, last week's price action. Catalyst Edge scans the source: SEC EDGAR filings. Every morning, the scanner processes 300+ new filings, classifies catalysts, scores tickers, and publishes a ranked watchlist before the market opens. The filing-first approach catches catalysts before they show up on price screens."),
            ("What you get for free",
             "The free tier includes: daily scanner results (gappers, value plays, moat builders), convergence alerts for the highest-conviction setups, SEC filing type breakdown, sector rotation heat map, and historical win/loss tracking. No credit card required, no trial period — just genuine daily analysis."),
            ("How scores work",
             "Each ticker receives a composite score based on: filing type weight (8-K material events score highest), insider activity (cluster buys boost the score), price momentum (gap history, relative strength), sector rotation (macro tailwinds/headwinds), and news sentiment. The final ranking combines all factors into a single actionable number."),
            ("Upgrade to Pro",
             "The free scanner publishes daily results. Pro subscribers ($39/mo) get: real-time convergence alerts via SMS + email, the Cerebro 3D market visualization HUD, sympathy chain tracking, options flow overlay, and squeeze radar. Pro is designed for active traders who need signals during the trading day, not just the morning scan."),
        ],
        "faqs": [
            ("Is the scanner really free?", "Yes. The daily scanner page at catalystedgescanner.com publishes results every trading day at no cost. Pro features (real-time alerts, Cerebro HUD) require a subscription."),
            ("When does the scanner update?", "The main scan runs at 4:05 AM ET on trading days (Monday-Friday). Results are published before 8 AM ET. Intraday updates run at 2 PM ET, and EOD recaps run from 3-8 PM ET."),
            ("How many stocks does the scanner cover?", "The scanner processes all SEC filings on EDGAR — covering 8,000+ publicly traded companies. The daily output focuses on the highest-scoring tickers across three categories: gappers, value plays, and moat builders."),
        ],
    },
    {
        "slug": "what-is-s3-shelf-registration",
        "title": "What is an S-3 Shelf Registration? SEC Filing Guide | Catalyst Edge",
        "description": "Learn what S-3 shelf registrations mean for traders, why they can be bullish or bearish, and how Catalyst Edge scores S-3 filings in context.",
        "h1": "What is an S-3 Shelf Registration?",
        "subtitle": "When Capital Raises Signal Opportunity, Not Dilution",
        "sections": [
            ("S-3 filing basics",
             "An S-3 is a simplified SEC registration form that allows a company to 'shelf register' securities for future sale. Once an S-3 is effective, the company can sell stock, debt, or warrants at any time within 3 years without filing a new registration. Think of it as pre-loading the ability to raise capital quickly."),
            ("Why S-3 filings are misunderstood",
             "Most retail traders see an S-3 filing and immediately assume 'dilution' — selling stock to raise cash at the expense of existing shareholders. While this is sometimes true, context matters enormously. Companies also file S-3s before positive catalysts (FDA approval, commercial launch) to raise growth capital. An S-3 paired with insider buying is often bullish, not bearish."),
            ("S-3 vs 424B prospectus supplements",
             "The S-3 is the shelf registration. The 424B is the actual pricing document for a specific offering. An S-3 alone means the company has the option to sell — it doesn't mean they will. A 424B supplement means they're actually selling, and the price and terms are set. Catalyst Edge distinguishes between S-3 registrations and 424B pricings in its scoring."),
            ("Trading around S-3 filings",
             "Key signals: S-3 + insider buying = bullish (management confident despite shelf). S-3 + 424B at market price = neutral (ATM offering, modest dilution). S-3 + 424B at steep discount = bearish (desperate capital raise). S-3 with no 424B for months = non-event (shelf expires unused). Catalyst Edge scores these combinations automatically."),
        ],
        "faqs": [
            ("Does an S-3 filing mean a stock will drop?", "Not necessarily. An S-3 grants the option to sell securities but doesn't require it. Many S-3 shelves expire without being used. The key is whether a 424B prospectus supplement follows, indicating an actual offering."),
            ("What is an ATM offering?", "An At-The-Market (ATM) offering allows a company to sell shares gradually at market price rather than a fixed price. ATMs cause less price impact than traditional offerings but create sustained selling pressure over weeks or months."),
        ],
    },
    {
        "slug": "sec-catalyst-trading-strategy",
        "title": "SEC Catalyst Trading Strategy: Filing-Based Edge | Catalyst Edge",
        "description": "Complete guide to SEC catalyst trading — using EDGAR filings as a primary signal source. Strategy, edge, tools, and daily execution workflow.",
        "h1": "SEC Catalyst Trading Strategy",
        "subtitle": "Building a Systematic Edge from Public Filings",
        "sections": [
            ("What is catalyst trading?",
             "Catalyst trading means positioning in stocks ahead of or immediately after material events that change the fundamental picture. Unlike technical analysis (which reads price patterns) or momentum trading (which follows trends), catalyst trading targets specific, identifiable events disclosed in SEC filings. The edge: filings are public, legally required, and often overlooked by retail traders."),
            ("The filing-first framework",
             "Step 1: Scan EDGAR for new filings daily. Step 2: Classify each filing by catalyst type (material event, insider buy, activist position). Step 3: Score tickers using a multi-factor model (filing type weight, insider activity, price momentum, sector context). Step 4: Build a ranked watchlist. Step 5: Execute trades based on the strongest convergence of signals."),
            ("Edge decay and timing",
             "SEC filings are public information, so the edge has a half-life. The initial window (filing published → mainstream media coverage) is typically 2-6 hours for material 8-K events. For less-covered small caps, the window can be 1-3 days. Catalyst Edge targets this window by scanning EDGAR overnight and publishing results before the pre-market session."),
            ("Risk management for catalyst trades",
             "Catalyst trades have asymmetric risk/reward but also binary risk. Rules: (1) Size positions based on catalyst conviction (material 8-K > routine filing), (2) Use hard stops — catalysts can fail, (3) Take partial profits at the gap level, (4) Never hold through a secondary catalyst (earnings, FDA) unless intentional, (5) Track win rates religiously — if the system isn't working, adjust."),
        ],
        "faqs": [
            ("What is the win rate for SEC catalyst trading?", "Catalyst Edge tracks its own performance transparently. Historical win rates are published on the scanner page. In general, material 8-K catalysts combined with insider buying have the highest hit rates (60-70% for a 2%+ intraday move)."),
            ("Can beginners use catalyst trading?", "Yes, but start with paper trading. The strategy is systematic (scan, score, rank, trade) which makes it learnable. The free Catalyst Edge scanner provides daily picks without requiring you to read filings yourself."),
            ("How is this different from news trading?", "News trading reacts to media headlines. Catalyst trading reads the primary source (SEC filings) before the media does. By the time a catalyst hits CNBC, the initial move is often 50-70% complete."),
        ],
    },
    {
        "slug": "what-is-squeeze-play",
        "title": "What is a Short Squeeze? Identifying Squeeze Candidates | Catalyst Edge",
        "description": "Understand short squeeze mechanics, how to identify squeeze candidates using short interest data and SEC filings, and how Catalyst Edge's squeeze radar works.",
        "h1": "What is a Short Squeeze?",
        "subtitle": "Mechanics, Signals, and How to Find Candidates",
        "sections": [
            ("Short squeeze mechanics",
             "A short squeeze occurs when a heavily shorted stock rises sharply, forcing short sellers to buy shares to cover their positions. This buying creates more upward pressure, forcing more shorts to cover, creating a feedback loop. The result: explosive, parabolic price moves that can send a stock up 50-500% in days. GameStop (GME) in January 2021 is the most famous example."),
            ("Identifying squeeze candidates",
             "The ingredients for a squeeze: (1) High short interest — 15%+ of float shorted, (2) Low float — fewer shares available means shorts are more trapped, (3) Rising borrow rate — harder to maintain short positions, (4) A catalyst — the spark that starts the covering. SEC filings provide the catalyst layer: an 8-K with positive news or insider buying can ignite a squeeze that pure price-action scanners miss."),
            ("The Catalyst Edge squeeze radar",
             "The scanner monitors all squeeze ingredients: short interest percentage, days-to-cover (how long it would take shorts to exit), borrow rates, float size, and SEC filing catalysts. Stocks are classified into stages: WATCH (conditions building), COILED (high short interest + catalyst detected), IGNITION (social media discovery + price breakout), and ACTIVE (squeeze in progress)."),
            ("Squeeze trading risks",
             "Squeezes are high-reward but high-risk. Timing is critical — entering too early means holding through pain, entering too late means buying the top. Always use stops. Size positions small relative to your portfolio. And remember: most squeeze candidates never actually squeeze. The ones that do require the convergence of high short interest, a real catalyst, and retail/institutional attention."),
        ],
        "faqs": [
            ("What short interest level indicates a potential squeeze?", "Generally, 15%+ of float shorted is considered elevated. Combined with a days-to-cover ratio above 5 and rising borrow rates, the conditions for a squeeze are forming. But without a catalyst (earnings beat, insider buying, viral social media attention), high short interest alone rarely triggers a squeeze."),
            ("How does Catalyst Edge find squeeze candidates?", "The squeeze radar cross-references short interest data with SEC filing catalysts. When a heavily shorted stock receives a positive 8-K filing or insider cluster buy, the system flags it as COILED — conditions are set for a potential squeeze."),
            ("Is short squeeze trading legal?", "Yes. Buying a stock because you believe it will go up — even if that belief is based on short squeeze potential — is legal. What's illegal is coordinating purchases to manipulate the price. Individual analysis and independent trading decisions are perfectly legal."),
        ],
    },
    {
        "slug": "what-is-convergence-alert",
        "title": "What is a Convergence Alert? Multi-Signal Trading | Catalyst Edge",
        "description": "Learn how convergence alerts combine multiple trading signals (SEC filings, insider buying, momentum, sector rotation) into high-conviction trade setups.",
        "h1": "What is a Convergence Alert?",
        "subtitle": "When Multiple Signals Fire on the Same Ticker",
        "sections": [
            ("Convergence defined",
             "A convergence alert fires when multiple independent trading signals align on the same ticker within a short time window. Instead of relying on a single indicator, convergence scoring combines 4-6 signals: SEC filing catalyst, insider buying, price momentum, sector rotation, social media sentiment, and options flow. When 3+ signals fire simultaneously, the probability of a profitable move increases significantly."),
            ("Why convergence beats single signals",
             "Any single signal can be noise. An 8-K filing might be routine. Insider buying might be a compensation plan exercise. Momentum might be a dead-cat bounce. But when a stock files a material 8-K, insiders buy aggressively, the sector is in rotation, and options flow turns bullish — all at the same time — that's a high-conviction setup."),
            ("How convergence scoring works",
             "Each signal type receives a weight based on historical predictive power. Material 8-K events have the highest base weight. Insider cluster buys multiply the score. Positive sector rotation adds a tailwind bonus. Social media attention (WSB mentions) adds momentum but with a lower weight due to noise. The final convergence score determines the alert level: ELEVATED (2-3 signals) or HIGH (4+ signals)."),
            ("Trading convergence alerts",
             "HIGH convergence alerts have historically produced the best win rates. Key rules: (1) Verify the catalyst is material (not routine), (2) Check that insider buying is open-market (not options exercise), (3) Confirm sector context is supportive, (4) Enter with a defined stop at the pre-catalyst price level, (5) Take partial profits at 3-5% gain, let runners ride with a trailing stop."),
        ],
        "faqs": [
            ("How many convergence alerts fire per day?", "On a typical trading day, 1-3 HIGH convergence alerts fire and 5-10 ELEVATED alerts. The system is intentionally selective — fewer, higher-quality signals produce better results than a flood of alerts."),
            ("Can I get convergence alerts on my phone?", "Pro subscribers receive convergence alerts via SMS and email in real-time. Free users see convergence alerts on the daily scanner page after 8 AM ET."),
            ("What's the difference between ELEVATED and HIGH?", "ELEVATED means 2-3 independent signals have fired on the same ticker. HIGH means 4+ signals are converging. HIGH alerts have historically produced larger moves and higher win rates."),
        ],
    },
]


# ── HTML template ──────────────────────────────────────────────────────────

def _faq_jsonld(faqs: list[tuple[str, str]]) -> str:
    items = []
    for q, a in faqs:
        items.append(f"""    {{
      "@type": "Question",
      "name": {json.dumps(q)},
      "acceptedAnswer": {{
        "@type": "Answer",
        "text": {json.dumps(a)}
      }}
    }}""")
    return ",\n".join(items)


def _related_links(current_slug: str) -> str:
    links = []
    for p in PAGES:
        if p["slug"] == current_slug:
            continue
        links.append(f'<a href="/glossary/{p["slug"]}/">{html_mod.escape(p["h1"])}</a>')
    return " &middot; ".join(links[:8])


def generate_page(page: dict) -> str:
    slug = page["slug"]
    sections_html = ""
    for title, content in page["sections"]:
        sections_html += f"""
    <section class="content-section">
      <h2>{html_mod.escape(title)}</h2>
      <p>{html_mod.escape(content)}</p>
    </section>"""

    faq_html = ""
    for q, a in page["faqs"]:
        faq_html += f"""
      <details class="faq-item">
        <summary>{html_mod.escape(q)}</summary>
        <p>{html_mod.escape(a)}</p>
      </details>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html_mod.escape(page["title"])}</title>
<meta name="description" content="{html_mod.escape(page["description"])}">
<link rel="canonical" href="{SITE}/glossary/{slug}/">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "FAQPage",
  "mainEntity": [
{_faq_jsonld(page["faqs"])}
  ]
}}
</script>
<style>
:root {{
  --bg: #0a0e1a;
  --surface: #111827;
  --surface-2: #1a2035;
  --border: #1e293b;
  --text: #e2e8f0;
  --text-dim: #94a3b8;
  --accent: #d4a853;
  --accent-glow: rgba(212, 168, 83, 0.15);
  --blue: #3b82f6;
  --green: #10b981;
  --red: #ef4444;
  --font: 'Space Grotesk', system-ui, sans-serif;
  --mono: 'IBM Plex Mono', monospace;
}}
*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  line-height: 1.7;
  -webkit-font-smoothing: antialiased;
}}
.container {{ max-width: 800px; margin: 0 auto; padding: 2rem 1.5rem; }}

/* Nav */
nav {{
  position: sticky; top: 0; z-index: 100;
  background: rgba(10, 14, 26, 0.95);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--border);
  padding: 0.75rem 1.5rem;
  display: flex; align-items: center; gap: 1rem;
}}
nav a {{ color: var(--accent); text-decoration: none; font-weight: 600; font-size: 0.95rem; }}
nav a:hover {{ text-decoration: underline; }}
nav .sep {{ color: var(--text-dim); }}

/* Hero */
.hero {{
  text-align: center;
  padding: 4rem 0 3rem;
  border-bottom: 1px solid var(--border);
  margin-bottom: 2rem;
}}
.hero h1 {{
  font-size: clamp(2rem, 5vw, 3rem);
  font-weight: 800;
  color: var(--accent);
  margin-bottom: 0.5rem;
  line-height: 1.2;
}}
.hero .subtitle {{
  font-size: 1.15rem;
  color: var(--text-dim);
  max-width: 600px;
  margin: 0 auto;
}}

/* Content sections */
.content-section {{
  margin-bottom: 2.5rem;
}}
.content-section h2 {{
  font-size: 1.4rem;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 0.75rem;
  padding-bottom: 0.5rem;
  border-bottom: 2px solid var(--accent-glow);
}}
.content-section p {{
  color: var(--text-dim);
  font-size: 1.05rem;
}}

/* FAQ */
.faq-section {{ margin-top: 3rem; }}
.faq-section h2 {{
  font-size: 1.4rem;
  font-weight: 700;
  margin-bottom: 1rem;
  color: var(--accent);
}}
.faq-item {{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  margin-bottom: 0.75rem;
  overflow: hidden;
}}
.faq-item summary {{
  padding: 1rem 1.25rem;
  font-weight: 600;
  cursor: pointer;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}}
.faq-item summary::before {{
  content: '+';
  font-family: var(--mono);
  color: var(--accent);
  font-size: 1.2rem;
  flex-shrink: 0;
}}
.faq-item[open] summary::before {{ content: '\u2212'; }}
.faq-item p {{
  padding: 0 1.25rem 1rem;
  color: var(--text-dim);
  line-height: 1.6;
}}

/* CTA */
.cta-box {{
  background: linear-gradient(135deg, var(--surface) 0%, var(--surface-2) 100%);
  border: 1px solid var(--accent);
  border-radius: 12px;
  padding: 2rem;
  text-align: center;
  margin: 3rem 0;
}}
.cta-box h3 {{
  color: var(--accent);
  font-size: 1.3rem;
  margin-bottom: 0.5rem;
}}
.cta-box p {{
  color: var(--text-dim);
  margin-bottom: 1.25rem;
}}
.cta-box a {{
  display: inline-block;
  background: var(--accent);
  color: var(--bg);
  font-weight: 700;
  padding: 0.75rem 2rem;
  border-radius: 8px;
  text-decoration: none;
  font-size: 1rem;
  transition: transform 0.2s, box-shadow 0.2s;
}}
.cta-box a:hover {{
  transform: translateY(-2px);
  box-shadow: 0 4px 20px var(--accent-glow);
}}

/* Related */
.related {{
  margin-top: 2rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border);
}}
.related h3 {{
  font-size: 1rem;
  color: var(--text-dim);
  margin-bottom: 0.75rem;
}}
.related a {{
  color: var(--blue);
  text-decoration: none;
  font-size: 0.9rem;
}}
.related a:hover {{ text-decoration: underline; }}

/* Footer */
footer {{
  text-align: center;
  padding: 2rem 0;
  color: var(--text-dim);
  font-size: 0.85rem;
  border-top: 1px solid var(--border);
  margin-top: 2rem;
}}
footer a {{ color: var(--accent); text-decoration: none; }}
</style>
</head>
<body>
<nav>
  <a href="/">Catalyst Edge</a>
  <span class="sep">/</span>
  <a href="/glossary/sec-filing-types-for-traders/">Glossary</a>
  <span class="sep">/</span>
  <span style="color:var(--text-dim);font-size:0.9rem">{html_mod.escape(page["h1"])}</span>
</nav>

<div class="container">
  <div class="hero">
    <h1>{html_mod.escape(page["h1"])}</h1>
    <p class="subtitle">{html_mod.escape(page["subtitle"])}</p>
  </div>
{sections_html}

  <div class="cta-box">
    <h3>Try the Free Scanner</h3>
    <p>Catalyst Edge scans 300+ SEC filings every day and publishes a ranked watchlist before market open.</p>
    <a href="{SITE}/">Open Scanner</a>
  </div>

  <div class="faq-section">
    <h2>Frequently Asked Questions</h2>
{faq_html}
  </div>

  <div class="related">
    <h3>Related Topics</h3>
    <p>{_related_links(slug)}</p>
  </div>
</div>

<footer>
  <a href="{SITE}/">Catalyst Edge Scanner</a> &middot;
  <a href="{AGENCY}">Daily Newsletter</a> &middot;
  &copy; 2026 Catalyst Edge
</footer>
</body>
</html>"""


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    generated = []
    for page in PAGES:
        slug = page["slug"]
        out_dir = GLOSSARY_DIR / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / "index.html"
        out_file.write_text(generate_page(page), encoding="utf-8")
        generated.append(slug)
        print(f"  glossary/{slug}/index.html")

    # List existing pages that aren't in this batch (manual/legacy)
    existing = set()
    if GLOSSARY_DIR.exists():
        for sub in GLOSSARY_DIR.iterdir():
            if sub.is_dir() and (sub / "index.html").exists():
                existing.add(sub.name)

    new_count = len(set(generated) - (existing - set(generated)))
    print(f"\nGenerated {len(generated)} glossary pages ({new_count} new)")
    print(f"Total glossary pages: {len(existing | set(generated))}")


if __name__ == "__main__":
    main()
