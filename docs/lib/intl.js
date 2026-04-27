/* docs/lib/intl.js — locale, time-zone, currency, number formatting helpers.
 *
 * No framework, no widget, no runtime page-translation. Browsers handle
 * page-language translation natively (Chrome / Edge / Safari / Firefox).
 *
 * What this file DOES handle:
 *   - User locale + timezone detection
 *   - Currency formatting respecting user's locale conventions
 *   - Date / number formatting per locale
 *   - Soft language-suggestion banner (sessionStorage-dismissible)
 *   - Currency code → symbol map for the markets we cover
 */

(function (global) {
  'use strict';

  var CURRENCY_BY_MARKET = {
    US: 'USD', BR: 'BRL', JP: 'JPY', UK: 'GBP', GB: 'GBP',
    IN: 'INR', MX: 'MXN', KR: 'KRW', HK: 'HKD', DE: 'EUR',
    FR: 'EUR', IT: 'EUR', ES: 'EUR', NL: 'EUR', AU: 'AUD',
    CA: 'CAD', CH: 'CHF', SG: 'SGD', AE: 'AED', IL: 'ILS',
    TR: 'TRY', ZA: 'ZAR', PL: 'PLN', SE: 'SEK', NO: 'NOK',
    DK: 'DKK', RU: 'RUB', CN: 'CNY', TW: 'TWD', TH: 'THB',
    ID: 'IDR', VN: 'VND', PH: 'PHP', MY: 'MYR'
  };

  // Locale → translated landing page route. Updated when Phase G ships pages.
  var LANG_TO_COUNTRY_PAGE = {
    pt: '/pt-br/',
    es: '/es/',
    hi: '/hi/',
    zh: '/zh/',
    ja: '/ja/',
    ko: '/ko/',
    de: '/de/',
    ar: '/ar/',
    fr: '/fr/'
  };

  function userLocale() {
    try {
      return (navigator.language || 'en-US').toString();
    } catch (e) {
      return 'en-US';
    }
  }

  function userLanguage() {
    return userLocale().split('-')[0].toLowerCase();
  }

  function userTimezone() {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    } catch (e) {
      return 'UTC';
    }
  }

  function currencyFor(market) {
    if (!market) return 'USD';
    return CURRENCY_BY_MARKET[market.toUpperCase()] || 'USD';
  }

  function formatCurrency(amount, currency, locale) {
    if (amount == null || isNaN(amount)) return '—';
    currency = (currency || 'USD').toUpperCase();
    locale = locale || userLocale();
    try {
      return new Intl.NumberFormat(locale, {
        style: 'currency', currency: currency,
        maximumFractionDigits: 2
      }).format(amount);
    } catch (e) {
      // Fallback if Intl rejects an unknown ISO code
      return currency + ' ' + Number(amount).toFixed(2);
    }
  }

  function formatNumber(n, locale, opts) {
    if (n == null || isNaN(n)) return '—';
    try {
      return new Intl.NumberFormat(locale || userLocale(), opts || {}).format(n);
    } catch (e) {
      return Number(n).toString();
    }
  }

  function formatPercent(n, locale, fractionDigits) {
    if (n == null || isNaN(n)) return '—';
    try {
      return new Intl.NumberFormat(locale || userLocale(), {
        style: 'percent', minimumFractionDigits: fractionDigits || 2,
        maximumFractionDigits: fractionDigits || 2
      }).format(n / 100);
    } catch (e) {
      return Number(n).toFixed(fractionDigits || 2) + '%';
    }
  }

  function formatDate(d, locale, opts) {
    if (!d) return '—';
    var date = (d instanceof Date) ? d : new Date(d);
    try {
      return new Intl.DateTimeFormat(locale || userLocale(),
        opts || { dateStyle: 'medium', timeStyle: 'short' }).format(date);
    } catch (e) {
      return date.toISOString();
    }
  }

  /**
   * Soft language-suggestion banner. Shows once per session. Never redirects.
   * The user dismisses it; sessionStorage remembers for that tab/session.
   * Call setupLanguageBanner() once on each page after DOM ready.
   */
  function setupLanguageBanner() {
    try {
      var lang = userLanguage();
      if (lang === 'en') return;
      var target = LANG_TO_COUNTRY_PAGE[lang];
      if (!target) return;
      // Don't show if user is already on the suggested page
      if (window.location.pathname.indexOf(target) === 0) return;
      var key = 'intl-banner-dismissed-' + lang;
      if (sessionStorage.getItem(key)) return;

      var labels = {
        pt: { msg: 'Disponível em Português',   cta: 'Ver versão →', dismiss: 'Dispensar' },
        es: { msg: 'Disponible en Español',     cta: 'Ver versión →', dismiss: 'Cerrar'    },
        hi: { msg: 'हिंदी संस्करण उपलब्ध',         cta: 'देखें →',          dismiss: 'बंद करें'   },
        zh: { msg: '中文版可用',                  cta: '查看 →',           dismiss: '关闭'      },
        ja: { msg: '日本語版もあります',           cta: '見る →',           dismiss: '閉じる'    },
        ko: { msg: '한국어 페이지 보기',           cta: '보기 →',           dismiss: '닫기'      },
        de: { msg: 'Auf Deutsch verfügbar',      cta: 'Anzeigen →',      dismiss: 'Schließen' },
        ar: { msg: 'متوفر باللغة العربية',         cta: 'عرض ←',            dismiss: 'إغلاق'    },
        fr: { msg: 'Disponible en Français',     cta: 'Voir →',          dismiss: 'Fermer'    }
      };
      var L = labels[lang] || labels.en;
      if (!L) return;

      var bar = document.createElement('div');
      bar.style.cssText = 'position:fixed;bottom:0;left:0;right:0;background:#0a66c2;color:white;padding:.75rem 1rem;display:flex;justify-content:center;align-items:center;gap:1rem;z-index:9999;font-size:.92rem;box-shadow:0 -2px 12px rgba(0,0,0,.15);font-family:-apple-system,BlinkMacSystemFont,Segoe UI,system-ui,sans-serif';
      var msg = document.createElement('span');
      msg.textContent = L.msg;
      var ctaA = document.createElement('a');
      ctaA.textContent = L.cta;
      ctaA.href = target;
      ctaA.style.cssText = 'color:white;font-weight:600;text-decoration:underline';
      var x = document.createElement('button');
      x.type = 'button';
      x.textContent = L.dismiss;
      x.style.cssText = 'background:transparent;border:1px solid rgba(255,255,255,.4);color:white;padding:.25rem .65rem;border-radius:4px;cursor:pointer;font-size:.85rem';
      x.onclick = function () {
        sessionStorage.setItem(key, '1');
        if (bar.parentNode) bar.parentNode.removeChild(bar);
      };
      bar.appendChild(msg);
      bar.appendChild(ctaA);
      bar.appendChild(x);
      document.body.appendChild(bar);
    } catch (e) { /* never break the page over a banner */ }
  }

  global.CatalystIntl = {
    userLocale: userLocale,
    userLanguage: userLanguage,
    userTimezone: userTimezone,
    currencyFor: currencyFor,
    formatCurrency: formatCurrency,
    formatNumber: formatNumber,
    formatPercent: formatPercent,
    formatDate: formatDate,
    setupLanguageBanner: setupLanguageBanner,
    CURRENCY_BY_MARKET: CURRENCY_BY_MARKET
  };
})(typeof window !== 'undefined' ? window : this);
