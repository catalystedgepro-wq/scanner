/* ext-summary.js — Catalyst Edge unified outbound-link summary tooltip.
 *
 * Drop-in module. Load this script on any page that has anchor elements with
 * the data-summary-* contract:
 *
 *   <a class="ext-link"
 *      href="https://www.sec.gov/..."
 *      target="_blank" rel="nofollow noopener"
 *      data-summary-ticker="HBIA"
 *      data-summary-form="8-K"
 *      data-summary-detail="Material corporate event — company required to disclose significant news · High-conviction setup — gap score 23 · No additional risk keywords were detected in the filing scan"
 *      data-cta-label="View Full Filing on EDGAR ↗">
 *      View Full Filing on EDGAR ↗
 *   </a>
 *
 * Behaviour:
 *  - On hover/focus, renders a tactical-panel tooltip above the anchor with
 *    ticker · form · detail · CTA label.
 *  - On touch devices, the first tap surfaces the tooltip; the second tap
 *    follows the link. (Desktop hover behavior unchanged.)
 *  - Accessibility: aria-describedby wired so screen readers see the summary
 *    when the anchor is focused.
 *  - All DOM construction is via createElement + textContent (no innerHTML).
 *
 * Pair with /lib/ext-summary.css for the visual layer.
 */
(function () {
  if (typeof document === "undefined") return;
  if (window.__ceExtSummaryLoaded) return;
  window.__ceExtSummaryLoaded = true;

  var TIP_ID = "ce-ext-summary-tooltip";

  function ensureTooltip() {
    var tip = document.getElementById(TIP_ID);
    if (tip) return tip;
    tip = document.createElement("div");
    tip.id = TIP_ID;
    tip.className = "ce-ext-tip";
    tip.setAttribute("role", "tooltip");
    tip.setAttribute("aria-hidden", "true");

    var head = document.createElement("div");
    head.className = "ce-ext-tip-head";

    var ticker = document.createElement("span");
    ticker.className = "ce-ext-tip-ticker";
    head.appendChild(ticker);

    var form = document.createElement("span");
    form.className = "ce-ext-tip-form";
    head.appendChild(form);

    var detail = document.createElement("div");
    detail.className = "ce-ext-tip-detail";

    var cta = document.createElement("div");
    cta.className = "ce-ext-tip-cta";

    tip.appendChild(head);
    tip.appendChild(detail);
    tip.appendChild(cta);

    document.body.appendChild(tip);
    return tip;
  }

  function fillTooltip(tip, anchor) {
    var t = anchor.getAttribute("data-summary-ticker") || "";
    var f = anchor.getAttribute("data-summary-form") || "";
    var d = anchor.getAttribute("data-summary-detail") || "";
    var c = anchor.getAttribute("data-cta-label") || (anchor.textContent || "").trim();

    tip.querySelector(".ce-ext-tip-ticker").textContent = t;
    var formEl = tip.querySelector(".ce-ext-tip-form");
    formEl.textContent = f;
    formEl.style.display = f ? "" : "none";
    tip.querySelector(".ce-ext-tip-detail").textContent = d;
    tip.querySelector(".ce-ext-tip-cta").textContent = c;
  }

  function position(tip, anchor) {
    var rect = anchor.getBoundingClientRect();
    var tipRect = tip.getBoundingClientRect();
    var pad = 12;
    var top = rect.top - tipRect.height - pad + window.scrollY;
    var left = rect.left + (rect.width / 2) - (tipRect.width / 2) + window.scrollX;

    // Flip below if not enough space above
    if (top < window.scrollY + pad) {
      top = rect.bottom + pad + window.scrollY;
      tip.classList.add("flip");
    } else {
      tip.classList.remove("flip");
    }

    // Clamp horizontally
    var minLeft = pad + window.scrollX;
    var maxLeft = window.scrollX + document.documentElement.clientWidth - tipRect.width - pad;
    if (left < minLeft) left = minLeft;
    if (left > maxLeft) left = maxLeft;

    tip.style.top = top + "px";
    tip.style.left = left + "px";
  }

  var currentAnchor = null;

  function show(anchor) {
    var tip = ensureTooltip();
    fillTooltip(tip, anchor);
    tip.classList.add("show");
    tip.setAttribute("aria-hidden", "false");
    // Position after layout (next tick so width measures correctly)
    requestAnimationFrame(function () { position(tip, anchor); });
    currentAnchor = anchor;
    // Wire aria-describedby so screen readers see it on focus
    anchor.setAttribute("aria-describedby", TIP_ID);
  }

  function hide() {
    var tip = document.getElementById(TIP_ID);
    if (!tip) return;
    tip.classList.remove("show");
    tip.setAttribute("aria-hidden", "true");
    if (currentAnchor) currentAnchor.removeAttribute("aria-describedby");
    currentAnchor = null;
  }

  function isExtLink(t) {
    return t && t.classList && t.classList.contains("ext-link");
  }

  // Mouse / focus
  document.addEventListener("mouseover", function (e) {
    var t = e.target.closest && e.target.closest(".ext-link");
    if (!t) return;
    show(t);
  });
  document.addEventListener("mouseout", function (e) {
    var t = e.target.closest && e.target.closest(".ext-link");
    if (!t) return;
    // Only hide if leaving to outside .ext-link (and not into tooltip)
    if (e.relatedTarget && (e.relatedTarget.closest(".ext-link") === t || e.relatedTarget.closest("#" + TIP_ID))) return;
    hide();
  });
  document.addEventListener("focusin", function (e) {
    if (isExtLink(e.target)) show(e.target);
  });
  document.addEventListener("focusout", function (e) {
    if (isExtLink(e.target)) hide();
  });

  // Touch: first tap shows tip, second tap (within 4s) follows link.
  var touchSeen = null;
  document.addEventListener("click", function (e) {
    var t = e.target.closest && e.target.closest(".ext-link");
    if (!t) return;
    // Skip mouse/keyboard events
    if (e.detail !== 0 && !window.matchMedia("(hover: none)").matches) return;
    if (touchSeen === t) {
      touchSeen = null;
      return; // let the navigation happen
    }
    e.preventDefault();
    touchSeen = t;
    show(t);
    setTimeout(function () { if (touchSeen === t) { touchSeen = null; hide(); } }, 4000);
  }, true);

  // Hide on scroll / resize
  window.addEventListener("scroll", hide, { passive: true });
  window.addEventListener("resize", hide);
  document.addEventListener("keydown", function (e) { if (e.key === "Escape") hide(); });
})();
