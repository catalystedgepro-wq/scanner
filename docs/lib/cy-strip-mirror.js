/* cy-strip-mirror.js — Mirror values from existing JS-populated elements
 * into the new cinematic strip cells without touching legacy data-fetch logic.
 *
 * Usage: add data-mirror="<source_id>" to any cin-strip cell value div.
 *
 *   <div class="cin-v" data-mirror="s-total">–</div>
 *
 * The script watches the source element for textContent changes and copies
 * to all targets. Runs after DOMContentLoaded and re-attaches observers
 * whenever new sources appear (handles delayed JS that creates the source).
 */
(function () {
  "use strict";
  if (typeof document === "undefined") return;

  function attachMirror(target) {
    var srcId = target.getAttribute("data-mirror");
    if (!srcId || target.dataset.mirrorAttached === "1") return;
    var src = document.getElementById(srcId);
    if (!src) return;
    target.dataset.mirrorAttached = "1";
    var update = function () {
      var v = (src.textContent || "").trim();
      if (v && v !== "–" && v !== "—" && v !== "--") target.textContent = v;
    };
    update();
    if (typeof MutationObserver !== "undefined") {
      var mo = new MutationObserver(update);
      mo.observe(src, { childList: true, characterData: true, subtree: true });
    }
  }

  function scan() {
    var nodes = document.querySelectorAll("[data-mirror]");
    for (var i = 0; i < nodes.length; i++) attachMirror(nodes[i]);
  }

  function init() {
    scan();
    setTimeout(scan, 500);
    setTimeout(scan, 1500);
    setTimeout(scan, 4000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
