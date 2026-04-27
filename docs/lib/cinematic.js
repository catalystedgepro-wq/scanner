/* docs/lib/cinematic.js — particle field + scroll-reveal for shared cinematic shell.
 * Pair with /lib/cinematic.css. Honors prefers-reduced-motion. */
(function(){
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

  // ── Particle canvas ──
  var c = document.getElementById('ce-particles');
  if (c) {
    var ctx = c.getContext('2d');
    var w = 0, h = 0, dpr = window.devicePixelRatio || 1;
    function resize() {
      w = window.innerWidth; h = window.innerHeight;
      c.width = w * dpr; c.height = h * dpr;
      c.style.width = w + 'px'; c.style.height = h + 'px';
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.scale(dpr, dpr);
    }
    resize();
    window.addEventListener('resize', resize);

    var N = Math.min(60, Math.floor((w * h) / 26000));
    var pts = [];
    for (var i = 0; i < N; i++) {
      pts.push({
        x: Math.random() * w, y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.18, vy: (Math.random() - 0.5) * 0.18,
        r: Math.random() * 1.4 + 0.4
      });
    }
    function tick() {
      ctx.clearRect(0, 0, w, h);
      for (var i = 0; i < pts.length; i++) {
        var p = pts[i];
        p.x += p.vx; p.y += p.vy;
        if (p.x < -10) p.x = w + 10;
        if (p.x > w + 10) p.x = -10;
        if (p.y < -10) p.y = h + 10;
        if (p.y > h + 10) p.y = -10;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(231,183,108,.5)';
        ctx.fill();
      }
      for (var i = 0; i < pts.length; i++) {
        for (var j = i + 1; j < pts.length; j++) {
          var dx = pts[i].x - pts[j].x, dy = pts[i].y - pts[j].y;
          var d2 = dx * dx + dy * dy;
          if (d2 < 9000) {
            var alpha = 0.14 * (1 - d2 / 9000);
            ctx.strokeStyle = 'rgba(114,229,255,' + alpha + ')';
            ctx.lineWidth = 0.6;
            ctx.beginPath();
            ctx.moveTo(pts[i].x, pts[i].y);
            ctx.lineTo(pts[j].x, pts[j].y);
            ctx.stroke();
          }
        }
      }
      requestAnimationFrame(tick);
    }
    tick();
  }

  // ── Scroll-reveal for sections, chapters, pull-quotes, callouts, tables ──
  if ('IntersectionObserver' in window) {
    var sel = '.ce-chapter, .ce-pull-quote, .ce-tablewrap, .ce-callout, .ce-card, .ce-stat, .ce-grid-3 > *, .ce-grid-4 > *, .ce-grid-auto > *';
    /* External-link intercept attached at the end of this file. */
    var obs = new IntersectionObserver(function(entries) {
      entries.forEach(function(e) {
        if (e.isIntersecting) {
          e.target.style.opacity = '1';
          e.target.style.transform = 'translateY(0)';
          obs.unobserve(e.target);
        }
      });
    }, { threshold: 0.12 });
    document.querySelectorAll(sel).forEach(function(el) {
      el.style.opacity = '0';
      el.style.transform = 'translateY(28px)';
      el.style.transition = 'opacity .85s cubic-bezier(.18,.84,.2,1), transform .85s cubic-bezier(.18,.84,.2,1)';
      obs.observe(el);
    });
  }
})();

/* ── EXTERNAL LINK INTERCEPT ──────────────────────────────────────────────
 * Show a cinematic preview modal before sending the user off-site.
 * Triggered by clicks on any anchor whose href is on a different host.
 * Skipped when the user is opening in a new tab (Cmd/Ctrl/Shift/middle-click)
 * or when the link explicitly opts out via data-no-intercept="1".
 * Uses safe DOM (createElement + textContent), no innerHTML. */
(function () {
  if (window.__ceExternalIntercept) return;
  window.__ceExternalIntercept = true;

  var SAME_ORIGIN_HOSTS = [
    'catalystedgescanner.com',
    'www.catalystedgescanner.com',
    'catalystedge.agency',
    'www.catalystedge.agency'
  ];
  var TRUSTED_PASSTHROUGH = ['buy.stripe.com', 'fonts.googleapis.com', 'fonts.gstatic.com'];

  function isSameOrigin(host) {
    if (!host) return true;
    host = host.toLowerCase();
    if (SAME_ORIGIN_HOSTS.indexOf(host) >= 0) return true;
    if (TRUSTED_PASSTHROUGH.indexOf(host) >= 0) return true;
    return false;
  }

  function injectStyle() {
    if (document.getElementById('ce-extlink-style')) return;
    var s = document.createElement('style');
    s.id = 'ce-extlink-style';
    s.textContent = [
      '.ce-extm{position:fixed;inset:0;z-index:9000;display:none;align-items:center;justify-content:center;',
      'background:rgba(0,0,0,.74);backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);',
      'padding:20px;animation:ceExtFade .22s ease}',
      '.ce-extm.open{display:flex}',
      '@keyframes ceExtFade{from{opacity:0}to{opacity:1}}',
      '@keyframes ceExtRise{from{transform:translateY(20px) scale(.97);opacity:0}to{transform:none;opacity:1}}',
      '.ce-extm-card{background:linear-gradient(135deg,rgba(20,16,22,.96),rgba(13,17,23,.96));',
      'border:1px solid rgba(231,183,108,.32);border-radius:16px;max-width:560px;width:100%;',
      'box-shadow:0 36px 90px rgba(0,0,0,.6),0 0 60px rgba(231,183,108,.18),inset 0 1px 0 rgba(255,255,255,.06);',
      'overflow:hidden;animation:ceExtRise .3s cubic-bezier(.18,.84,.2,1);font-family:"Space Grotesk",sans-serif}',
      '.ce-extm-head{display:flex;align-items:center;gap:10px;padding:16px 20px;',
      'border-bottom:1px solid rgba(255,255,255,.08);background:rgba(0,0,0,.22)}',
      '.ce-extm-tag{font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.2em;',
      'text-transform:uppercase;color:#e7b76c;font-weight:700}',
      '.ce-extm-tag::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;',
      'background:#e7b76c;margin-right:8px;vertical-align:middle;animation:ceExtPulse 1.6s ease-in-out infinite}',
      '@keyframes ceExtPulse{0%,100%{opacity:1}50%{opacity:.4}}',
      '.ce-extm-spacer{flex:1}',
      '.ce-extm-close{background:transparent;border:none;color:#7a8899;font-size:24px;line-height:1;',
      'cursor:pointer;padding:0 6px;transition:color .15s,transform .15s;font-weight:300}',
      '.ce-extm-close:hover{color:#e7b76c;transform:scale(1.1)}',
      '.ce-extm-body{padding:22px 24px 8px}',
      '.ce-extm-h{font-size:18px;font-weight:700;color:#e8edf4;margin-bottom:8px;letter-spacing:-.005em}',
      '.ce-extm-h .ce-extm-acc{color:#e7b76c}',
      '.ce-extm-host{font-family:"IBM Plex Mono",monospace;font-size:13px;color:#72e5ff;',
      'background:rgba(114,229,255,.06);border:1px solid rgba(114,229,255,.22);',
      'padding:8px 12px;border-radius:6px;margin:10px 0 14px;word-break:break-all}',
      '.ce-extm-warn{font-size:12.5px;color:#7a8899;background:rgba(0,0,0,.28);',
      'border-left:3px solid rgba(231,183,108,.4);padding:8px 12px;border-radius:0 6px 6px 0;',
      'margin-bottom:14px;line-height:1.55}',
      '.ce-extm-warn b{color:#e7b76c}',
      '.ce-extm-actions{display:flex;gap:10px;padding:14px 24px 20px;flex-wrap:wrap;justify-content:flex-end;',
      'background:rgba(0,0,0,.18);border-top:1px solid rgba(255,255,255,.05)}',
      '.ce-extm-btn{display:inline-flex;align-items:center;gap:6px;padding:10px 18px;border-radius:8px;',
      'font-weight:700;font-size:13px;text-decoration:none;cursor:pointer;border:none;',
      'transition:filter .15s,transform .15s,box-shadow .15s;font-family:inherit;border-bottom:none}',
      '.ce-extm-btn.primary{background:linear-gradient(135deg,#e7b76c,#c89854);color:#0a0d18;',
      'box-shadow:0 0 22px rgba(231,183,108,.3)}',
      '.ce-extm-btn.primary:hover{filter:brightness(1.08);transform:translateY(-1px);color:#0a0d18}',
      '.ce-extm-btn.secondary{background:transparent;color:#7a8899;border:1px solid #30363d}',
      '.ce-extm-btn.secondary:hover{color:#e8edf4;border-color:#7a8899}',
      '@media(max-width:520px){.ce-extm-actions{justify-content:stretch}.ce-extm-btn{flex:1;justify-content:center}}'
    ].join('');
    document.head.appendChild(s);
  }

  function buildModal() {
    if (document.getElementById('ce-extm')) return document.getElementById('ce-extm');
    var modal = document.createElement('div');
    modal.id = 'ce-extm'; modal.className = 'ce-extm';
    modal.setAttribute('role', 'dialog');
    modal.setAttribute('aria-modal', 'true');
    modal.setAttribute('aria-hidden', 'true');

    var card = document.createElement('div');
    card.className = 'ce-extm-card';

    var head = document.createElement('div');
    head.className = 'ce-extm-head';
    var tag = document.createElement('span');
    tag.className = 'ce-extm-tag';
    tag.textContent = 'External Link';
    head.appendChild(tag);
    head.appendChild(Object.assign(document.createElement('span'), { className: 'ce-extm-spacer' }));
    var closeBtn = document.createElement('button');
    closeBtn.className = 'ce-extm-close';
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Close');
    closeBtn.textContent = '×';
    head.appendChild(closeBtn);

    var body = document.createElement('div');
    body.className = 'ce-extm-body';
    var h = document.createElement('div');
    h.className = 'ce-extm-h';
    h.id = 'ce-extm-h';
    body.appendChild(h);
    var hostBlock = document.createElement('div');
    hostBlock.className = 'ce-extm-host';
    hostBlock.id = 'ce-extm-host';
    body.appendChild(hostBlock);
    var warn = document.createElement('div');
    warn.className = 'ce-extm-warn';
    warn.appendChild(document.createTextNode('Clicking '));
    var b = document.createElement('b');
    b.textContent = 'Continue to source';
    warn.appendChild(b);
    warn.appendChild(document.createTextNode(' opens the link in a new tab. You\'ll leave catalystedgescanner.com.'));
    body.appendChild(warn);

    var actions = document.createElement('div');
    actions.className = 'ce-extm-actions';
    var stay = document.createElement('button');
    stay.className = 'ce-extm-btn secondary';
    stay.id = 'ce-extm-stay';
    stay.type = 'button';
    stay.textContent = 'Stay here';
    var go = document.createElement('a');
    go.className = 'ce-extm-btn primary';
    go.id = 'ce-extm-go';
    go.target = '_blank';
    go.rel = 'nofollow noopener noreferrer';
    go.textContent = 'Continue to source ↗';
    actions.appendChild(stay);
    actions.appendChild(go);

    card.appendChild(head);
    card.appendChild(body);
    card.appendChild(actions);
    modal.appendChild(card);
    document.body.appendChild(modal);

    function closeModal() {
      modal.classList.remove('open');
      modal.setAttribute('aria-hidden', 'true');
      document.body.style.overflow = '';
    }
    closeBtn.addEventListener('click', function (ev) { ev.stopPropagation(); closeModal(); });
    stay.addEventListener('click', function (ev) { ev.stopPropagation(); closeModal(); });
    modal.addEventListener('click', function (e) { if (e.target === modal) closeModal(); });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && modal.classList.contains('open')) closeModal();
    });
    /* "Continue" anchor: let it navigate naturally; close after the new tab opens. */
    go.addEventListener('click', function () { setTimeout(closeModal, 50); });
    return modal;
  }

  function open(opts) {
    injectStyle();
    var modal = buildModal();
    var hEl = document.getElementById('ce-extm-h');
    var hostEl = document.getElementById('ce-extm-host');
    var goBtn = document.getElementById('ce-extm-go');
    if (hEl) {
      hEl.replaceChildren();
      hEl.appendChild(document.createTextNode((opts.label || 'You\'re leaving Catalyst Edge') + ' '));
      var acc = document.createElement('span');
      acc.className = 'ce-extm-acc';
      acc.textContent = '↗';
      hEl.appendChild(acc);
    }
    if (hostEl) {
      hostEl.replaceChildren();
      hostEl.appendChild(document.createTextNode(opts.host || ''));
    }
    if (goBtn && opts.href) goBtn.setAttribute('href', opts.href);
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
  }

  document.addEventListener('click', function (e) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1) return;
    /* Critical: skip clicks inside our own modal so the "Continue to source"
       anchor + "Stay here" / × buttons aren't re-intercepted into a loop. */
    if (e.target.closest && e.target.closest('.ce-extm')) return;
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a) return;
    if (a.getAttribute('data-no-intercept') === '1') return;
    /* Skip if this anchor already wires the SEC filing-thesis intercept (data-summary). */
    if (a.hasAttribute('data-summary')) return;
    var href = a.getAttribute('href');
    if (!href || href.charAt(0) === '#' || href.indexOf('mailto:') === 0 || href.indexOf('tel:') === 0) return;
    var url;
    try { url = new URL(href, window.location.href); }
    catch (_) { return; }
    if (url.protocol !== 'http:' && url.protocol !== 'https:') return;
    if (isSameOrigin(url.hostname)) return;
    e.preventDefault();
    var label = (a.textContent || '').trim().replace(/\s+/g, ' ');
    if (label.length > 60) label = label.slice(0, 57) + '…';
    open({ host: url.hostname, href: url.href, label: label || 'External source' });
  }, true);
})();

/* ── STRIPE client_reference_id ──────────────────────────────────────────
 * Append a per-visitor UUID to all buy.stripe.com links at click time so we
 * can correlate Stripe webhook events back to specific browsers/funnel sources.
 * Does NOT block navigation. Reuses the same UUID across pages for a session. */
(function () {
  if (window.__ceStripeRef) return;
  window.__ceStripeRef = true;

  function uuid() {
    /* Lightweight UUIDv4 (RFC4122 §4.4). Crypto-strong if available, else fallback. */
    if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
    var r = (window.crypto && crypto.getRandomValues)
      ? crypto.getRandomValues(new Uint8Array(16))
      : Array.from({length:16}, function(){ return Math.floor(Math.random()*256); });
    r[6] = (r[6] & 0x0f) | 0x40;
    r[8] = (r[8] & 0x3f) | 0x80;
    var hex = Array.from(r, function(b){ return ('0'+b.toString(16)).slice(-2); }).join('');
    return hex.slice(0,8)+'-'+hex.slice(8,12)+'-'+hex.slice(12,16)+'-'+hex.slice(16,20)+'-'+hex.slice(20);
  }

  function getRef() {
    try {
      var k = 'ce_ref';
      var v = sessionStorage.getItem(k);
      if (!v) { v = uuid(); sessionStorage.setItem(k, v); }
      return v;
    } catch (_) { return uuid(); }
  }

  document.addEventListener('click', function (e) {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button === 1) return;
    var a = e.target.closest && e.target.closest('a[href*="buy.stripe.com"]');
    if (!a) return;
    try {
      var url = new URL(a.href);
      if (!url.hostname.endsWith('stripe.com')) return;
      if (!url.searchParams.has('client_reference_id')) {
        url.searchParams.set('client_reference_id', getRef());
        /* Tag the funnel source for analytics */
        var src = location.pathname.replace(/\/$/, '').split('/').filter(Boolean).pop() || 'home';
        if (!url.searchParams.has('utm_source')) url.searchParams.set('utm_source', 'catalyst-edge');
        if (!url.searchParams.has('utm_medium')) url.searchParams.set('utm_medium', src);
        a.href = url.toString();
      }
    } catch (_) { /* ignore */ }
  }, true);
})();
