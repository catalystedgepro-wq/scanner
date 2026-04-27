/* docs/lib/tier.js — single source of truth for user tier across all pages.
 *
 *   tier ∈ { 'free', 'reader', 'pro' }
 *
 * Detection order:
 *   1. URL param ?unlock=REPLACE_WITH_YOUR_ADMIN_TOKEN → admin (= pro), persist to
 *      localStorage AND a long-lived cookie (so HUD works across origins).
 *   2. localStorage 'edge_admin' === admin token → pro.
 *   3. /api/tier endpoint → server-set tier (cookie-based reader/pro).
 *   4. Default 'free'.
 *
 *   CatalystTier.get() → string tier (synchronous best-known)
 *   CatalystTier.onResolved(cb) → cb(tier) when /api/tier replies
 *   CatalystTier.attachUnlockOverlay(rowEl, opts) → adds clickable "Unlock $9
 *      / $39" overlay over a blurred row, linking to /pricing/?from=<page>.
 */

(function (global) {
  'use strict';
  var ADMIN_TOKEN = 'REPLACE_WITH_YOUR_ADMIN_TOKEN';
  var COOKIE_DAYS = 365;
  var STATE = { tier: 'free', resolved: false, listeners: [] };

  function setCookie(name, val, days) {
    try {
      var d = new Date();
      d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000);
      document.cookie = name + '=' + encodeURIComponent(val)
        + '; expires=' + d.toUTCString()
        + '; path=/; samesite=lax';
    } catch (e) {}
  }

  function getCookie(name) {
    try {
      var m = document.cookie.match(new RegExp('(?:^|;\\s*)' + name + '=([^;]+)'));
      return m ? decodeURIComponent(m[1]) : '';
    } catch (e) { return ''; }
  }

  function notify() {
    STATE.resolved = true;
    var ls = STATE.listeners; STATE.listeners = [];
    ls.forEach(function (cb) { try { cb(STATE.tier); } catch (e) {} });
  }

  function setTier(t) {
    var ranked = { free: 0, reader: 1, pro: 2 };
    if ((ranked[t] || 0) > (ranked[STATE.tier] || 0)) {
      STATE.tier = t;
      document.body && document.body.setAttribute('data-tier', t);
    }
  }

  // Monkey-patch fetch so legacy pages calling /api/tier get admin = pro
  // transparently, with no per-page edits needed.
  function installFetchOverride() {
    if (typeof window === 'undefined' || !window.fetch || window.__catalystTierPatched) return;
    var origFetch = window.fetch;
    window.fetch = function (input, init) {
      var u = typeof input === 'string' ? input :
        (input && input.url) ? input.url : '';
      if (u.indexOf('/api/tier') === 0 || /\/api\/tier(\?|$)/.test(u)) {
        return Promise.resolve(new Response(
          JSON.stringify({ tier: 'pro', source: 'admin-bypass' }),
          { status: 200, headers: { 'content-type': 'application/json' } }
        ));
      }
      return origFetch.apply(this, arguments);
    };
    window.__catalystTierPatched = true;
  }

  function init() {
    // 1. URL token bypass — visiting any page with ?unlock=<token> persists.
    try {
      var url = new URL(window.location.href);
      if (url.searchParams.get('unlock') === ADMIN_TOKEN) {
        localStorage.setItem('edge_admin', ADMIN_TOKEN);
        setCookie('edge_admin', ADMIN_TOKEN, COOKIE_DAYS);
        url.searchParams.delete('unlock');
        var clean = url.pathname + (url.search || '') + url.hash;
        window.history.replaceState({}, '', clean);
      }
    } catch (e) {}
    var isAdmin = false;
    try { isAdmin = (localStorage.getItem('edge_admin') === ADMIN_TOKEN); } catch (e) {}
    if (!isAdmin && getCookie('edge_admin') === ADMIN_TOKEN) isAdmin = true;
    if (isAdmin) {
      // Promote tier and intercept any /api/tier call so legacy pages unlock too.
      setTier('pro');
      installFetchOverride();
      // Mark body classes for CSS-based legacy paywall hides.
      var apply = function () {
        if (!document.body) return;
        document.body.classList.add('edge-pro-unlocked');
        document.body.classList.add('edge-reader-unlocked');
        document.body.classList.add('edge-admin');
      };
      if (document.body) apply();
      else document.addEventListener('DOMContentLoaded', apply);
      notify();
      return;
    }

    fetch('/api/tier', { credentials: 'include', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) {
        if (d && d.tier && ['free', 'reader', 'pro'].indexOf(d.tier) !== -1) {
          setTier(d.tier);
          var apply = function () {
            if (!document.body) return;
            if (d.tier === 'pro') {
              document.body.classList.add('edge-pro-unlocked');
              document.body.classList.add('edge-reader-unlocked');
            } else if (d.tier === 'reader') {
              document.body.classList.add('edge-reader-unlocked');
            }
          };
          if (document.body) apply();
          else document.addEventListener('DOMContentLoaded', apply);
        }
        notify();
      })
      .catch(function () { notify(); });
  }

  function get() { return STATE.tier; }
  function isPaid() { return STATE.tier === 'reader' || STATE.tier === 'pro'; }
  function isPro() { return STATE.tier === 'pro'; }

  function onResolved(cb) {
    if (STATE.resolved) {
      try { cb(STATE.tier); } catch (e) {}
    } else {
      STATE.listeners.push(cb);
    }
  }

  /* attachUnlockOverlay — wraps a blurred element with an absolutely
   * positioned clickable "Unlock" badge. Caller is responsible for
   * giving the parent `position: relative`. */
  function attachUnlockOverlay(parent, opts) {
    if (!parent) return;
    if (parent.querySelector('.tier-unlock-overlay')) return;
    opts = opts || {};
    var minTier = opts.minTier || 'reader';
    var price = minTier === 'pro' ? '$39' : '$9';
    var label = (opts.label || 'Unlock — ' + price + '/mo');
    var page = encodeURIComponent(window.location.pathname);
    var ov = document.createElement('a');
    ov.className = 'tier-unlock-overlay';
    ov.href = '/pricing/?from=' + page + '&min=' + minTier;
    ov.textContent = '🔒 ' + label;
    ov.style.cssText =
      'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;'
      + 'background:linear-gradient(180deg, rgba(7,9,15,0) 0%, rgba(7,9,15,0.55) 60%, rgba(7,9,15,0.85) 100%);'
      + 'color:#f6efe2;font-family:"IBM Plex Mono",monospace;font-size:.78rem;'
      + 'font-weight:700;letter-spacing:.08em;text-transform:uppercase;'
      + 'text-decoration:none;border-radius:inherit;'
      + 'pointer-events:auto;cursor:pointer;z-index:5;'
      + 'border:1px solid rgba(215,180,106,.4);'
      + 'transition:background .15s ease, transform .12s ease;';
    ov.onmouseover = function () {
      ov.style.background = 'linear-gradient(180deg, rgba(215,180,106,0.15), rgba(215,180,106,0.35))';
      ov.style.color = '#07090f';
      ov.style.borderColor = '#d7b46a';
    };
    ov.onmouseout = function () {
      ov.style.background = 'linear-gradient(180deg, rgba(7,9,15,0) 0%, rgba(7,9,15,0.55) 60%, rgba(7,9,15,0.85) 100%)';
      ov.style.color = '#f6efe2';
      ov.style.borderColor = 'rgba(215,180,106,.4)';
    };
    parent.appendChild(ov);
  }

  global.CatalystTier = {
    get: get, isPaid: isPaid, isPro: isPro,
    onResolved: onResolved,
    attachUnlockOverlay: attachUnlockOverlay,
    ADMIN_TOKEN: ADMIN_TOKEN,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(typeof window !== 'undefined' ? window : this);
