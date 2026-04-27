# Security Audit — Catalyst Edge Scanner
**Date:** 2026-04-27 · **Scope:** every public page on catalystedgescanner.com + catalystedge.agency

## Summary verdict

**1 CRITICAL · 2 HIGH · 4 MEDIUM · 3 LOW · 0 confirmed exploit.**
No live secret leak. Nothing actually breached. Three architectural findings worth fixing
this sprint, two worth fixing later.

---

## ✅ CLEAN — confirmed not exploitable

### A. Hardcoded API keys / secrets in public docs
**Searched for** `AKIA*`, `sk-proj-*`, `sk_live_*`, `xoxb-*`, `ghp_*`, `pk_live_*`, `whsec_*`, raw Bearer tokens.
**Result:** ZERO matches in `docs/`. No secrets in shipped HTML/JS/CSS.

### B. Sensitive-file path traversal
Tested 9 paths (`/.env`, `/.git/config`, `/agent_coinbase.py`, `/.sec_email_env`,
`/.live_strategy.json`, `/requirements.txt`, `/package.json`, `/node_modules/`,
`/.agent_coinbase_halted`).

All return HTTP 200 — but the body is the SPA fallback `index.html` (516KB),
not the actual file. None of those files exist at `/opt/catalyst/docs/` on the droplet.
Confirmed via `ssh ls` — `cannot access '/opt/catalyst/docs/.env'`.
**Bottom line:** no real exposure, just nginx try_files fallback.

### C. CORS posture
- Origin `https://catalystedgescanner.com` → `access-control-allow-origin: https://catalystedgescanner.com` ✓
- Origin `https://evil.example` → no ACAO header returned → browser blocks the response
- `access-control-allow-credentials: true` is set, but without a matching ACAO it's not exploitable
**Bottom line:** restrictive same-origin posture. Safe.

### D. Mixed content
Zero `http://` references in `/scanner/`, `/`, `/landing/`, `/agency/`, `/short-scanner/`.
All resources load over HTTPS.

### E. External script origins (only two third-party scripts)
- `https://www.googletagmanager.com/gtag/js` (Google Analytics 4) — expected
- `https://elevenlabs.io/convai-widget/index.js` (voice agent on `/agency/`) — expected
**Recommendation:** add SRI hashes to lock these to specific versions.

---

## 🔴 CRITICAL — fix this sprint

### 1. Admin token is a viewable secret in client-side code
**File:** `docs/lib/tier.js` line 22 + 4 other files (`hud/index.html`, `jackpot/index.html`, `dcf/index.html`).
**Token:** `REPLACE_WITH_YOUR_ADMIN_TOKEN`
**Impact:** Any visitor who opens DevTools or views source can grant themselves Pro/admin tier by either:
1. Visiting any page with `?unlock=REPLACE_WITH_YOUR_ADMIN_TOKEN`
2. Running `localStorage.setItem('edge_admin', 'REPLACE_WITH_YOUR_ADMIN_TOKEN')` in console
3. Setting cookie `edge_admin=REPLACE_WITH_YOUR_ADMIN_TOKEN` directly

This bypasses the entire paywall. The first paying customer (cwbrab@gmail.com) and anyone else
paying $9 is paying for something a 5-second source-view defeats.

**Why it's like this:** by design — operator (you) needed a portable admin override that works
across browsers/devices without a server login.

**Fix path (3 options, ranked):**
1. **Best:** server-side `/api/tier` becomes the only source of truth. Client never holds a token.
   Admin signs in via a one-time email magic link. Stripe webhook → DB → `/api/tier` returns `pro`.
2. **Acceptable:** rotate the admin token to a HMAC-signed format like
   `admin:{userid}:{expiry}:{hmac(SECRET, userid+expiry)}`. Server validates the HMAC. Token is
   user-specific and time-bound. Browser-side code can't forge it without the SECRET.
3. **Minimum:** rotate `REPLACE_WITH_YOUR_ADMIN_TOKEN` quarterly + obfuscate (won't stop a real attacker but
   raises friction).

---

## 🟠 HIGH

### 2. No CSP / no security headers
**Missing on every response:**
- `Content-Security-Policy`
- `X-Frame-Options` (clickjacking)
- `Strict-Transport-Security` (HSTS)
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy`
- `Permissions-Policy`

**Impact:** if any of the existing `innerHTML` calls were ever fed untrusted data, no CSP would
catch it. The page can be embedded in an iframe (clickjacking surface). Browsers won't enforce
HTTPS-only after the first visit.

**Fix:** add to nginx config in the `catalystedgescanner.com` server block:
```nginx
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload" always;
add_header X-Frame-Options "SAMEORIGIN" always;
add_header X-Content-Type-Options "nosniff" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Permissions-Policy "camera=(), microphone=(), geolocation=()" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline' https://www.googletagmanager.com https://elevenlabs.io https://convai-widget.elevenlabs.io https://buy.stripe.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self' https://www.google-analytics.com; frame-src https://buy.stripe.com" always;
```
Note: `'unsafe-inline'` for `style-src` and `script-src` is a concession to the existing inline
styles/scripts. Tightening to nonce-based CSP requires a per-request nonce mechanism.

### 3. Twenty-one `innerHTML` usages on the homepage scanner — content-trust review needed
**Files:** `docs/scanner/index.html` (21 instances), `docs/index.html` (21 instances — same file regenerated).
**Audit findings on the 10 sampled lines:**
- Lines 3702, 4223, 4435 — `innerHTML = ''` (clear) — SAFE (no injection)
- Line 3805 — subscribe success — static literal — SAFE
- Line 4416 — snapshot mode label — static literal — SAFE
- Line 4533, 4570, 4658 — INJECT API DATA — **REVIEW NEEDED**
- Line 4698, 4861 — Polymarket fallback message — static literal — SAFE

**Risk:** lines 4533/4570/4658 inject scanner data into `innerHTML`. If any field in the API
response (ticker symbol, summary, headline) ever contained `<script>` tags or `onerror=` HTML
attributes, it would execute. The API source is `sec_catalyst_latest.csv` which we control,
so the realistic risk is low — but the pattern is fragile. Refactor to safe DOM
(createElement + textContent + appendChild).

---

## 🟡 MEDIUM

### 4. tier.js uses `localStorage` — phishable
A phishing page that resembles catalystedgescanner.com can pre-set `localStorage.edge_admin`
via XSS — but only if XSS is found first. No XSS found, so this is theoretical.

### 5. Stripe checkout URLs are direct/unsigned
Anyone can craft a URL like `https://buy.stripe.com/aFa4gt4Da1yKeKq2z2f7i01?prefilled_email=victim@example.com`.
Not a vulnerability, but means subscription emails could be spoofed at the checkout step.
Recommendation: use Stripe's `client_reference_id` to bind checkouts to your own user IDs.

### 6. Cloudflare proxy (`server: cloudflare`)
Means CF can see all request bodies including subscriber emails on the form posts. This is fine
if CF is acceptable in your threat model — most SaaS uses them — but worth flagging.

### 7. Form-POST for email subscription uses plain `mailto:` action
Some forms (`/enterprise/`) use `<form action="mailto:opensource@example.com" method="POST">`.
Modern browsers handle this oddly. Recommendation: replace with a real `/api/contact` endpoint.

---

## 🟢 LOW

### 8. ElevenLabs convai widget on `/agency/`
Loaded from `elevenlabs.io`. Trusted vendor but third-party. Add SRI hash + harden CSP.

### 9. Google Analytics 4 (gtag.js)
Loaded sitewide. Trusted vendor. Add SRI hash + harden CSP.

### 10. `tier.js` monkey-patches `window.fetch`
The fetch override intercepts `/api/tier` calls and short-circuits to `'pro'` for admin.
Defensive practice — but a clever XSS could exploit the monkey-patched fetch to spoof other
endpoints. Refactor: use `Response.json()` properly, scope override more narrowly.

---

## Action plan (recommended order)

| # | Task | Effort | Impact |
|---|------|--------|--------|
| 1 | Add nginx security headers (HSTS, X-Frame-Options, nosniff, Referrer-Policy, Permissions-Policy) | 15 min | HIGH |
| 2 | Move admin tier check to server-side (HMAC-signed cookie or DB-backed `/api/tier`) | 1–2 days | CRITICAL |
| 3 | Refactor 3 `innerHTML` calls (4533/4570/4658) to safe DOM | 30 min | HIGH |
| 4 | Add SRI hashes to ElevenLabs + GA4 script tags | 10 min | LOW |
| 5 | Replace `mailto:` form actions with `/api/contact` POST | 1 hour | MEDIUM |
| 6 | Bind Stripe checkouts via `client_reference_id` | 30 min | MEDIUM |
| 7 | Add CSP (start in `Content-Security-Policy-Report-Only` mode) | 1 hour | HIGH |
| 8 | Quarterly admin-token rotation (until #2 ships) | recurring | CRITICAL stopgap |

## Verification commands (re-run any time)

```bash
# Re-test secret leak surface
grep -rnE 'AKIA[0-9A-Z]{16}|sk-proj-|sk_live_|xoxb-|ghp_|pk_live_|whsec_' docs/ | grep -v node_modules

# Re-test sensitive file fallback
for p in /.env /.git/config /agent_coinbase.py; do
  curl -s --max-time 4 "https://catalystedgescanner.com$p" | head -1 | head -c 80
done

# Re-test security headers
curl -s -I --max-time 6 "https://catalystedgescanner.com/" | grep -iE "strict-transport|x-frame|x-content|csp|referrer|permissions"

# Re-test CORS posture
curl -s -I --max-time 5 -H "Origin: https://evil.example" "https://catalystedgescanner.com/api/momentum" | grep -i access-control
```

---

*Audit run by Claude · 2026-04-27 · Output committed alongside source for transparency.*
