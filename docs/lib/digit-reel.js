/* docs/lib/digit-reel.js — animated digit reel renderer (port of /scanner/
 * ph-reel pattern). Replaces a numeric value with per-digit reels that
 * spin to the new digit when the value changes.
 *
 *   CatalystReels.render(hostEl, value, { decimals, prefix, suffix });
 *   CatalystReels.update(hostEl, newValue);
 *
 * Each digit lives in its own .ph-reel; only the digits that changed
 * animate.
 */

(function (global) {
  'use strict';

  function buildReels(host, valueStr) {
    while (host.firstChild) host.removeChild(host.firstChild);
    host.classList.add('ph-reels');
    for (var i = 0; i < valueStr.length; i++) {
      var ch = valueStr[i];
      if (ch >= '0' && ch <= '9') {
        var reel = document.createElement('span');
        reel.className = 'ph-reel';
        reel.dataset.digit = ch;
        var inner = document.createElement('span');
        inner.textContent = ch;
        reel.appendChild(inner);
        host.appendChild(reel);
      } else {
        var sep = document.createElement('span');
        sep.textContent = ch;
        sep.style.padding = '0 1px';
        host.appendChild(sep);
      }
    }
  }

  function update(host, newValue, opts) {
    opts = opts || {};
    var prefix = opts.prefix || '';
    var suffix = opts.suffix || '';
    var decimals = (opts.decimals != null) ? opts.decimals : 2;
    var formatted;
    if (newValue == null || isNaN(newValue)) {
      formatted = '—';
    } else {
      var sign = (opts.signed && newValue >= 0) ? '+' : '';
      formatted = prefix + sign + Number(newValue).toFixed(decimals) + suffix;
    }
    var existing = Array.from(host.querySelectorAll('.ph-reel'));
    if (!existing.length) {
      buildReels(host, formatted);
      return;
    }
    // Walk through existing reels and update digits with animation
    var idx = 0;
    var spans = host.childNodes;
    var fIdx = 0;
    for (var s = 0; s < spans.length && fIdx < formatted.length; s++) {
      var el = spans[s];
      var ch = formatted[fIdx];
      if (el.classList && el.classList.contains('ph-reel')) {
        if (el.dataset.digit !== ch && ch >= '0' && ch <= '9') {
          el.dataset.digit = ch;
          var inner = el.firstChild;
          if (inner) {
            inner.classList.remove('spinning');
            inner.textContent = ch;
            // Force reflow so animation re-runs
            void inner.offsetWidth;
            inner.classList.add('spinning');
          }
        }
        fIdx++;
      } else if (el.nodeType === 1 || el.nodeType === 3) {
        if (el.textContent !== ch) {
          el.textContent = ch;
        }
        fIdx++;
      }
    }
    // If the formatted string is longer/shorter than existing reels, rebuild.
    if (fIdx !== formatted.length || existing.length !== formatted.replace(/[^0-9]/g, '').length) {
      buildReels(host, formatted);
    }
  }

  function render(host, value, opts) {
    opts = opts || {};
    update(host, value, opts);
    if (opts.flash) {
      host.classList.remove('live-tick-flash');
      void host.offsetWidth;
      host.classList.add('live-tick-flash');
    }
  }

  global.CatalystReels = { render: render, update: update };
})(typeof window !== 'undefined' ? window : this);
