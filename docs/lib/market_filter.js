/* docs/lib/market_filter.js — multi-select market filter chip component.
 *
 * Reusable across /scanner/, /international/, /defi/, country pages, and the
 * HUD. Default state = all markets selected (unified scanner). Country pages
 * pre-set their market on init.
 *
 * Usage:
 *   var mf = CatalystMarketFilter.create(containerEl, {
 *     markets: ['US','BR','JP','UK','IN','MX','KR','HK','DE','AU','CA'],
 *     selected: 'all',                  // or ['US','BR']
 *     onChange: function(selected){ ... } // selected is array of codes
 *   });
 */

(function (global) {
  'use strict';

  var FLAGS = {
    US:'🇺🇸', BR:'🇧🇷', JP:'🇯🇵', UK:'🇬🇧', GB:'🇬🇧', IN:'🇮🇳',
    MX:'🇲🇽', KR:'🇰🇷', HK:'🇭🇰', DE:'🇩🇪', FR:'🇫🇷', AU:'🇦🇺',
    CA:'🇨🇦', CN:'🇨🇳', AE:'🇦🇪', SG:'🇸🇬', IL:'🇮🇱', TR:'🇹🇷',
    ZA:'🇿🇦', RU:'🇷🇺', SE:'🇸🇪', CH:'🇨🇭', ID:'🇮🇩', TH:'🇹🇭',
    VN:'🇻🇳', PH:'🇵🇭', MY:'🇲🇾', PL:'🇵🇱', NL:'🇳🇱', IT:'🇮🇹', ES:'🇪🇸'
  };

  var NAMES = {
    US:'United States', BR:'Brazil', JP:'Japan', UK:'United Kingdom',
    GB:'United Kingdom', IN:'India', MX:'Mexico', KR:'South Korea',
    HK:'Hong Kong', DE:'Germany', FR:'France', AU:'Australia',
    CA:'Canada', CN:'China', AE:'United Arab Emirates', SG:'Singapore',
    IL:'Israel', TR:'Turkey', ZA:'South Africa', RU:'Russia',
    SE:'Sweden', CH:'Switzerland', ID:'Indonesia', TH:'Thailand',
    VN:'Vietnam', PH:'Philippines', MY:'Malaysia', PL:'Poland',
    NL:'Netherlands', IT:'Italy', ES:'Spain'
  };

  function clearChildren(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  function create(container, opts) {
    if (!container) return null;
    opts = opts || {};
    var markets = opts.markets || ['US','BR','JP','UK','IN','MX','KR','HK','DE','AU','CA'];
    var initial = opts.selected;
    var selected;
    if (initial === 'all' || !initial) selected = markets.slice();
    else if (Array.isArray(initial)) selected = initial.slice();
    else selected = [String(initial)];
    var onChange = opts.onChange || function () {};

    clearChildren(container);
    container.style.cssText += ';display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,system-ui,sans-serif;';

    var label = document.createElement('span');
    label.textContent = 'Markets:';
    label.style.cssText = 'color:#94a3b8;font-size:.85rem;font-weight:500;margin-right:.25rem';
    container.appendChild(label);

    function chipStyle(active) {
      return 'cursor:pointer;border:1px solid ' + (active ? '#22d3ee' : '#2a3554')
        + ';background:' + (active ? 'rgba(34,211,238,.12)' : 'transparent')
        + ';color:' + (active ? '#e6ecf5' : '#94a3b8')
        + ';padding:.3rem .65rem;border-radius:999px;font-size:.82rem;'
        + 'transition:all .15s ease;user-select:none;display:inline-flex;align-items:center;gap:.3rem';
    }

    var chips = {};
    function paint() {
      Object.keys(chips).forEach(function (m) {
        chips[m].style.cssText = chipStyle(selected.indexOf(m) !== -1);
      });
      allBtn.style.cssText = chipStyle(selected.length === markets.length);
    }

    var allBtn = document.createElement('button');
    allBtn.type = 'button';
    allBtn.textContent = 'All';
    allBtn.title = 'Select all markets';
    allBtn.style.cssText = chipStyle(true);
    allBtn.onclick = function () {
      if (selected.length === markets.length) selected = [];
      else selected = markets.slice();
      paint();
      onChange(selected.slice());
    };
    container.appendChild(allBtn);

    markets.forEach(function (m) {
      var b = document.createElement('button');
      b.type = 'button';
      b.title = NAMES[m] || m;
      b.dataset.market = m;
      var flag = document.createElement('span');
      flag.textContent = FLAGS[m] || '';
      var code = document.createElement('span');
      code.textContent = m;
      b.appendChild(flag);
      b.appendChild(code);
      b.onclick = function () {
        var i = selected.indexOf(m);
        if (i === -1) selected.push(m);
        else selected.splice(i, 1);
        paint();
        onChange(selected.slice());
      };
      chips[m] = b;
      container.appendChild(b);
    });

    paint();

    return {
      getSelected: function () { return selected.slice(); },
      setSelected: function (arr) {
        selected = (arr === 'all') ? markets.slice() : arr.slice();
        paint();
        onChange(selected.slice());
      },
      isSelected: function (m) { return selected.indexOf(m) !== -1; }
    };
  }

  global.CatalystMarketFilter = {
    create: create,
    FLAGS: FLAGS,
    NAMES: NAMES
  };
})(typeof window !== 'undefined' ? window : this);
