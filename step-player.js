/* ==========================================================================
   forged-kit — step-player.js
   Reference implementation of the Forged Tools step-player contract
   (see PLAYER.md). Vanilla JS, no dependencies, no build step. Vendored
   as-is into static Pages sites alongside forged.css + step-player.css.

   API:
     FkStepPlayer.mount(containerEl, script, {
       render: (step, index, prevIndex) => void,   // required
       onConcept: (key, concept, event) => void    // optional
     }) -> controller { goTo, next, prev, index(), step(), destroy }

     FkStepPlayer.applyHighlights(rootEl, highlights)  // optional helper

   Ownership: the player owns navigation, narration, progress, concept
   chips, and the data-fk-step-active attribute on the container. It never
   touches the domain canvas — all canvas drawing happens inside the
   render callback supplied by the domain.
   ========================================================================== */
(function (global) {
  "use strict";

  var HL_KINDS = ["focus", "pulse", "dim", "reveal"];
  var HL_SELECTOR = HL_KINDS.map(function (k) { return ".fk-hl-" + k; }).join(",");

  var KATEX_OPTS = {
    delimiters: [
      { left: "$$", right: "$$", display: true },
      { left: "\\[", right: "\\]", display: true },
      { left: "\\(", right: "\\)", display: false }
    ],
    throwOnError: false
  };

  /* ---------------------------------------------------------------- utils */

  function el(tag, className, parent) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (parent) parent.appendChild(node);
    return node;
  }

  function validateScript(script) {
    if (!script || typeof script !== "object") {
      throw new Error("FkStepPlayer: script must be an object");
    }
    if (!Array.isArray(script.steps) || script.steps.length === 0) {
      throw new Error("FkStepPlayer: script.steps must be a non-empty array");
    }
    var seen = {};
    script.steps.forEach(function (step, i) {
      if (!step || typeof step !== "object") {
        throw new Error("FkStepPlayer: steps[" + i + "] is not an object");
      }
      if (step.id != null) {
        if (seen[step.id]) {
          throw new Error("FkStepPlayer: duplicate step id '" + step.id + "'");
        }
        seen[step.id] = true;
      }
    });
  }

  /* --------------------------------------------------------- highlights */

  /* Resolve a highlight target within rootEl. Resolution order:
     1. elements whose data-fk-target attribute equals the target string;
     2. failing that, the target string used as a raw CSS selector.
     Invalid selectors resolve to no elements (never throw). */
  function resolveTargets(rootEl, target) {
    var found = [];
    try {
      var esc = (global.CSS && CSS.escape)
        ? CSS.escape(target)
        : String(target).replace(/["\\]/g, "\\$&");
      found = rootEl.querySelectorAll('[data-fk-target="' + esc + '"]');
    } catch (e) { /* fall through */ }
    if (found.length) return Array.prototype.slice.call(found);
    try {
      return Array.prototype.slice.call(rootEl.querySelectorAll(target));
    } catch (e) {
      return [];
    }
  }

  /* Clear all four fk-hl-* classes under (and on) rootEl, then apply the
     given highlight list. Unknown kinds default to "focus". Domains may
     call this from their render callback, or ignore it entirely and do
     their own highlighting. */
  function applyHighlights(rootEl, highlights) {
    if (!rootEl || !rootEl.querySelectorAll) return;
    var stale = Array.prototype.slice.call(rootEl.querySelectorAll(HL_SELECTOR));
    if (rootEl.classList) stale.push(rootEl);
    stale.forEach(function (node) {
      HL_KINDS.forEach(function (k) { node.classList.remove("fk-hl-" + k); });
    });
    if (!Array.isArray(highlights)) return;
    highlights.forEach(function (hl) {
      if (!hl || typeof hl.target !== "string") return;
      var kind = HL_KINDS.indexOf(hl.kind) >= 0 ? hl.kind : "focus";
      var cls = "fk-hl-" + kind;
      resolveTargets(rootEl, hl.target).forEach(function (node) {
        if (kind === "pulse" || kind === "reveal") {
          /* force reflow so re-applied animations restart */
          node.classList.remove(cls);
          void node.offsetWidth;
        }
        node.classList.add(cls);
      });
    });
  }

  /* -------------------------------------------------------------- mount */

  function mount(containerEl, script, options) {
    if (!containerEl || containerEl.nodeType !== 1) {
      throw new Error("FkStepPlayer.mount: containerEl must be a DOM element");
    }
    validateScript(script);
    options = options || {};
    if (typeof options.render !== "function") {
      throw new Error("FkStepPlayer.mount: options.render callback is required");
    }

    /* --- build player chrome (container content is replaced) --- */
    containerEl.innerHTML = "";
    containerEl.classList.add("fk-step-player");

    var progress = el("div", "fk-sp-progress", containerEl);
    progress.setAttribute("role", "progressbar");
    progress.setAttribute("aria-label", "Step progress");
    var progressFill = el("div", "fk-sp-progress-fill", progress);

    var head = el("div", "fk-sp-head", containerEl);
    var titleNode = el("h3", "fk-sp-title", head);
    var counter = el("span", "fk-sp-counter", head);

    var narration = el("div", "fk-card fk-sp-narration", containerEl);
    narration.setAttribute("aria-live", "polite");

    var conceptsRow = el("div", "fk-sp-concepts", containerEl);

    var nav = el("div", "fk-sp-nav", containerEl);
    var prevBtn = el("button", "fk-btn fk-sp-btn fk-sp-prev", nav);
    prevBtn.type = "button";
    prevBtn.innerHTML = "&larr; Prev";
    var nextBtn = el("button", "fk-btn fk-sp-btn fk-sp-next", nav);
    nextBtn.type = "button";
    nextBtn.innerHTML = "Next &rarr;";

    var total = script.steps.length;
    var index = -1;
    var destroyed = false;

    /* --- per-step chrome updates (player-owned surfaces only) --- */

    function renderConcepts(step) {
      conceptsRow.innerHTML = "";
      var keys = Array.isArray(step.concepts) ? step.concepts : [];
      var defs = script.concepts || {};
      keys.forEach(function (key) {
        var def = defs[key];
        if (!def || !def.url) return;
        var chip = el("a", "fk-chip fk-sp-concept", conceptsRow);
        chip.href = def.url;
        chip.target = "_blank";
        chip.rel = "noopener";
        chip.textContent = def.label || key;
        if (typeof options.onConcept === "function") {
          chip.addEventListener("click", function (ev) {
            options.onConcept(key, def, ev);
          });
        }
      });
      conceptsRow.hidden = conceptsRow.children.length === 0;
    }

    function goTo(target) {
      if (destroyed) return;
      if (typeof target !== "number" || target < 0 || target >= total) return;
      if (target === index) return;
      var prevIndex = index;
      index = target;
      var step = script.steps[index];

      /* bookkeeping attribute — the only DOM state the player writes
         outside its own chrome */
      containerEl.setAttribute("data-fk-step-active",
        step.id != null ? String(step.id) : String(index));

      titleNode.textContent = step.title || "";
      counter.textContent = "Step " + (index + 1) + " / " + total;
      progressFill.style.width = (((index + 1) / total) * 100) + "%";
      progress.setAttribute("aria-valuenow", String(index + 1));
      progress.setAttribute("aria-valuemin", "1");
      progress.setAttribute("aria-valuemax", String(total));

      narration.innerHTML = step.narration || "";
      /* KaTeX auto-render, if the host page loaded it */
      if (typeof global.renderMathInElement === "function") {
        try { global.renderMathInElement(narration, KATEX_OPTS); }
        catch (e) { /* narration stays as raw delimiters */ }
      }

      renderConcepts(step);
      prevBtn.disabled = (index === 0);
      nextBtn.disabled = (index === total - 1);

      /* the domain draws its canvas; player passes payload through opaque */
      options.render(step, index, prevIndex);
    }

    function next() { goTo(index + 1); }
    function prev() { goTo(index - 1); }

    /* --- events --- */

    prevBtn.addEventListener("click", prev);
    nextBtn.addEventListener("click", next);

    function onKey(ev) {
      if (ev.defaultPrevented || ev.altKey || ev.ctrlKey || ev.metaKey) return;
      var t = ev.target;
      if (t && (/^(input|textarea|select)$/i.test(t.tagName) || t.isContentEditable)) return;
      if (ev.key === "ArrowLeft") { prev(); ev.preventDefault(); }
      else if (ev.key === "ArrowRight") { next(); ev.preventDefault(); }
    }
    document.addEventListener("keydown", onKey);

    function destroy() {
      if (destroyed) return;
      destroyed = true;
      document.removeEventListener("keydown", onKey);
      containerEl.removeAttribute("data-fk-step-active");
      containerEl.classList.remove("fk-step-player");
      containerEl.innerHTML = "";
    }

    /* initial render: prevIndex is -1 by contract */
    goTo(0);

    return {
      goTo: goTo,
      next: next,
      prev: prev,
      index: function () { return index; },
      step: function () { return script.steps[index]; },
      destroy: destroy
    };
  }

  /* -------------------------------------------------------------- export */

  var FkStepPlayer = { mount: mount, applyHighlights: applyHighlights };

  if (typeof module === "object" && module.exports) {
    module.exports = FkStepPlayer;
  }
  global.FkStepPlayer = FkStepPlayer;

})(typeof window !== "undefined" ? window : this);
