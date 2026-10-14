/* Semantic Search Engine UI — client side behaviour
   Theme, navigation, tabs, sliders, conditional form fields, collection
   filters, form busy states. No framework, no build step. */

const THEME_KEY = "sse-theme";
const THEME_ORDER = ["auto", "light", "dark"];

/* ------------------------------------------------------------------- i18n */
// Texts of the current interface language, rendered by base.html from
// app/locales/<lang>.json (section "js"). Plural entries hold CLDR forms
// (one / few / many / other) selected with Intl.PluralRules.
const I18N = (() => {
  try {
    return JSON.parse(document.getElementById("i18n-data")?.textContent || "{}");
  } catch (error) {
    return {};
  }
})();
const LANG = I18N.lang || document.documentElement.lang || "en";
const TEXTS = I18N.texts || {};

function fill(template, vars) {
  return String(template).replace(/\{(\w+)\}/g, (match, name) =>
    name in vars ? String(vars[name]) : match
  );
}

function t(key, vars = {}, fallback = key) {
  const value = TEXTS[key];
  if (value === undefined || value === null) return fill(fallback, vars);
  if (typeof value === "object") {
    const n = Number(vars.n) || 0;
    let category = "other";
    try {
      category = new Intl.PluralRules(LANG).select(n);
    } catch (error) {
      category = n === 1 ? "one" : "other";
    }
    return fill(value[category] ?? value.other ?? value.many ?? fallback, vars);
  }
  return fill(value, vars);
}

/* ------------------------------------------------------------------ theme */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch (error) {
    // The selected theme still applies when browser storage is unavailable.
  }
}

function initThemeToggle() {
  const button = document.querySelector(".theme-toggle");
  if (!button) return;
  button.addEventListener("click", () => {
    const current = document.documentElement.dataset.theme || "auto";
    const next = THEME_ORDER[(THEME_ORDER.indexOf(current) + 1) % THEME_ORDER.length];
    applyTheme(next);
    button.setAttribute("title", themeTitle(next));
  });
  button.setAttribute("title", themeTitle(document.documentElement.dataset.theme || "auto"));
}

function themeTitle(theme) {
  return t("theme_title", { theme: t(`theme_${theme}`, {}, theme) }, "Theme: {theme} (click to change)");
}

/* ------------------------------------------------------------ navigation */
function initNavToggle() {
  const toggle = document.querySelector(".nav-toggle");
  const nav = document.querySelector("#primary-nav");
  if (!toggle || !nav) return;

  toggle.addEventListener("click", () => {
    const open = nav.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", String(open));
  });
  nav.addEventListener("click", (event) => {
    if (event.target.closest("a")) {
      nav.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
    }
  });
}

/* ------------------------------------------------------------------ tabs */
// ARIA tabs: a [data-tabs] list of [role="tab"] buttons, each controlling the
// panel referenced by aria-controls. Only one panel is visible at a time.
function initTabs() {
  document.querySelectorAll("[data-tabs]").forEach((tabList) => {
    const tabs = Array.from(tabList.querySelectorAll('[role="tab"]'));
    const panels = tabs
      .map((tab) => document.getElementById(tab.getAttribute("aria-controls")))
      .filter(Boolean);
    if (!tabs.length) return;

    const activate = (tab, moveFocus) => {
      const target = tab.getAttribute("aria-controls");
      tabs.forEach((candidate) => {
        const selected = candidate === tab;
        candidate.classList.toggle("is-active", selected);
        candidate.setAttribute("aria-selected", String(selected));
        candidate.tabIndex = selected ? 0 : -1;
      });
      panels.forEach((panel) => panel.classList.toggle("is-active", panel.id === target));
      if (moveFocus) tab.focus();
    };

    tabs.forEach((tab, position) => {
      tab.addEventListener("click", () => activate(tab, false));
      tab.addEventListener("keydown", (event) => {
        const steps = { ArrowRight: 1, ArrowLeft: -1 };
        if (event.key in steps) {
          event.preventDefault();
          activate(tabs[(position + steps[event.key] + tabs.length) % tabs.length], true);
        } else if (event.key === "Home") {
          event.preventDefault();
          activate(tabs[0], true);
        } else if (event.key === "End") {
          event.preventDefault();
          activate(tabs[tabs.length - 1], true);
        }
      });
    });
  });
}

/* --------------------------------------------------- expandable table text */
function initClamps() {
  document.querySelectorAll("[data-clamp]").forEach((element) => {
    const toggle = () => {
      const opened = element.classList.toggle("is-open");
      element.setAttribute("aria-expanded", String(opened));
    };
    element.addEventListener("click", toggle);
    element.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        toggle();
      }
    });
  });
}

/* ------------------------------------------------ score bars (0..1 values) */
// With data-score-max the bar is relative to the best hit: engine scores
// (e.g. after rank fusion) can be tiny in absolute terms.
function initScoreBars() {
  document.querySelectorAll("[data-score]").forEach((bar) => {
    const value = Number(bar.dataset.score);
    if (!Number.isFinite(value)) return;
    const max = Number(bar.dataset.scoreMax);
    const ratio = Number.isFinite(max) && max > 0
      ? value / max
      : value > 1 ? value / 100 : value;
    bar.style.setProperty("--score", `${Math.max(0, Math.min(1, ratio)) * 100}%`);
  });
}

/* ------------------------------------------------- results: view switch */
// [data-view-switch] holds [data-view] buttons and [data-view-panel] blocks;
// the chosen view is remembered for the next search.
function initViewSwitches() {
  document.querySelectorAll("[data-view-switch]").forEach((root, index) => {
    const buttons = Array.from(root.querySelectorAll("[data-view]"));
    const panels = Array.from(root.querySelectorAll("[data-view-panel]"));
    const key = `sse-view-${root.closest("[role='tabpanel']")?.id || index}`;

    const show = (view) => {
      buttons.forEach((button) => {
        const active = button.dataset.view === view;
        button.classList.toggle("is-active", active);
        button.setAttribute("aria-pressed", String(active));
      });
      panels.forEach((panel) => {
        panel.hidden = panel.dataset.viewPanel !== view;
      });
    };

    buttons.forEach((button) =>
      button.addEventListener("click", () => {
        show(button.dataset.view);
        try {
          localStorage.setItem(key, button.dataset.view);
        } catch (error) {
          /* storage unavailable */
        }
      })
    );

    let saved = null;
    try {
      saved = localStorage.getItem(key);
    } catch (error) {
      /* storage unavailable */
    }
    if (saved && buttons.some((button) => button.dataset.view === saved)) show(saved);
  });
}

/* ------------------------------------------- results: filter by document */
function initHitFilters() {
  document.querySelectorAll(".doc-filter").forEach((group) => {
    const root = group.closest("[data-view-switch]") || document;
    const chips = Array.from(group.querySelectorAll("[data-hit-filter]"));
    chips.forEach((chip) =>
      chip.addEventListener("click", () => {
        const doc = chip.dataset.hitFilter;
        chips.forEach((other) => {
          const active = other === chip;
          other.classList.toggle("is-active", active);
          other.setAttribute("aria-pressed", String(active));
        });
        root.querySelectorAll("[data-hit]").forEach((hit) => {
          hit.hidden = Boolean(doc) && hit.dataset.doc !== doc;
        });
      })
    );
  });
}

/* ----------------------------------------- results: expand long passages */
function initHitExpanders() {
  document.querySelectorAll("[data-hit-expand]").forEach((button) => {
    const text = document.getElementById(button.getAttribute("aria-controls"));
    if (!text) return;
    const label = button.textContent;
    button.addEventListener("click", () => {
      const opened = text.classList.toggle("is-open");
      button.setAttribute("aria-expanded", String(opened));
      button.textContent = opened ? t("show_less", {}, "Show less") : label;
    });
  });
}

/* ------------------------------------ results: highlight the query words */
// Words of the question (4+ letters) are matched by their stem, so inflected
// forms ("ofertowe" / "ofertowego") are highlighted too. Works on text nodes
// only, the passage text is never parsed as HTML.
const HIGHLIGHT_STOPWORDS = new Set([
  "oraz", "jest", "jako", "które", "który", "która", "czego", "czym", "jaki", "jakie",
  "jaka", "kiedy", "gdzie", "dlaczego", "przez", "tego", "temu", "albo", "lub",
  "what", "which", "where", "when", "with", "from", "that", "this", "does", "have",
  "about", "there", "their", "sample", "question", "przykładowe", "pytanie",
  "jaką", "jakim", "jakich", "można", "należy",
]);

function initHighlights() {
  document.querySelectorAll("[data-highlight]").forEach((root) => {
    const stems = Array.from(
      new Set(
        (root.dataset.highlight.toLowerCase().match(/[\p{L}\p{N}]+/gu) || [])
          .filter((word) => word.length >= 4 && !HIGHLIGHT_STOPWORDS.has(word))
          .map((word) => word.slice(0, Math.max(4, word.length - 2)))
      )
    );
    if (!stems.length) return;

    const escaped = stems.map((stem) => stem.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const pattern = new RegExp(`(?<![\\p{L}\\p{N}])(?:${escaped.join("|")})[\\p{L}\\p{N}]*`, "giu");

    root.querySelectorAll("[data-hit-text]").forEach((element) => {
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      const nodes = [];
      while (walker.nextNode()) nodes.push(walker.currentNode);

      nodes.forEach((node) => {
        const text = node.nodeValue;
        pattern.lastIndex = 0;
        if (!pattern.test(text)) return;
        pattern.lastIndex = 0;

        const fragment = document.createDocumentFragment();
        let last = 0;
        for (const match of text.matchAll(pattern)) {
          fragment.append(text.slice(last, match.index));
          const mark = document.createElement("mark");
          mark.className = "hit__mark";
          mark.textContent = match[0];
          fragment.append(mark);
          last = match.index + match[0].length;
        }
        fragment.append(text.slice(last));
        node.replaceWith(fragment);
      });
    });
  });
}

/* ---------------------------------------------------------- copy buttons */
function initCopyButtons(root = document) {
  root.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const target = document.getElementById(button.dataset.copy);
      if (!target) return;
      const text = target.innerText.trim();
      try {
        await navigator.clipboard.writeText(text);
      } catch (error) {
        const area = document.createElement("textarea");
        area.value = text;
        document.body.appendChild(area);
        area.select();
        document.execCommand("copy");
        area.remove();
      }
      const label = button.textContent;
      button.textContent = t("copied", {}, "Copied");
      button.disabled = true;
      window.setTimeout(() => {
        button.textContent = label;
        button.disabled = false;
      }, 1500);
    });
  });
}

/* --------------------------------------------------------------- sliders */
function paintRange(range) {
  const min = Number(range.min || 0);
  const max = Number(range.max || 100);
  const value = Number(range.value || 0);
  const ratio = max === min ? 0 : ((value - min) / (max - min)) * 100;
  range.style.setProperty("--range-progress", `${ratio}%`);
}

function initSliders() {
  document.querySelectorAll(".field-slider").forEach((row) => {
    const range = row.querySelector("input[type='range']");
    const output = row.querySelector("output");
    if (!range) return;

    const sync = () => {
      if (output) output.textContent = range.value;
      paintRange(range);
    };
    range.addEventListener("input", sync);
    sync();
  });
}

/* --------------------------------------------------------- upload summary */
function initFileSummary() {
  const fileInput = document.querySelector("[data-file-summary]");
  if (!fileInput) return;

  const summary = document.querySelector(fileInput.dataset.fileSummary);
  if (!summary) return;

  const render = () => {
    const files = Array.from(fileInput.files || []);
    if (!files.length) {
      summary.textContent = t("no_files", {}, "No files selected yet.");
      return;
    }

    const bytes = files.reduce((total, file) => total + file.size, 0);
    const number = new Intl.NumberFormat(LANG, { maximumFractionDigits: 1 });
    const size = bytes > 1048576
      ? `${number.format(bytes / 1048576)} MB`
      : `${Math.max(1, Math.round(bytes / 1024))} KB`;
    summary.textContent = t(
      "files_selected",
      { n: files.length, size },
      "{n} file(s) selected · {size}"
    );
  };

  fileInput.addEventListener("change", render);
  render();
}

/* ------------------------------------------------------- upload dropzone */
function initDropzone() {
  document.querySelectorAll("[data-dropzone]").forEach((zone) => {
    const input = zone.querySelector("input[type='file']");
    const setActive = (active) => zone.classList.toggle("is-dragover", active);
    ["dragenter", "dragover"].forEach((name) =>
      zone.addEventListener(name, () => setActive(true))
    );
    ["dragleave", "drop"].forEach((name) =>
      zone.addEventListener(name, () => setActive(false))
    );
    if (input) {
      input.addEventListener("change", () =>
        zone.classList.toggle("has-files", Boolean(input.files && input.files.length))
      );
    }
  });
}

/* ------------------------------------------------------ chunking preview */
// Visualises the chunk/overlap ratio chosen with the indexing sliders.
function initChunkPreview() {
  const preview = document.querySelector("[data-chunk-preview]");
  if (!preview) return;
  const form = preview.closest("form") || document;
  const chunk = form.querySelector("input[name='max_tokens_in_chunk']");
  const overlap = form.querySelector("input[name='number_of_overlap_tokens']");
  if (!chunk || !overlap) return;

  const render = () => {
    const size = Math.max(1, Number(chunk.value) || 1);
    const ratio = Math.max(0, Math.min(0.9, (Number(overlap.value) || 0) / size));
    preview.style.setProperty("--overlap", ratio.toFixed(3));
  };
  chunk.addEventListener("input", render);
  overlap.addEventListener("input", render);
  render();
}

/* ------------------------------------------------------- example queries */
function initExamples() {
  const question = document.getElementById("question");
  if (!question) return;
  document.querySelectorAll("[data-example]").forEach((button) => {
    button.addEventListener("click", () => {
      question.value = button.textContent.trim();
      question.focus();
    });
  });
}

/* ------------------------------------------- conditional form sections */
function toggleBlock(target, visible) {
  if (target) target.classList.toggle("hidden", !visible);
}

function initConditionalFields() {
  const generativeToggle = document.getElementById("use_qa_generative");
  const generativeBlock = document.getElementById("generative-qa-block");
  if (generativeToggle && generativeBlock) {
    toggleBlock(generativeBlock, generativeToggle.checked);
    generativeToggle.addEventListener("change", () =>
      toggleBlock(generativeBlock, generativeToggle.checked)
    );
  }

  const translateToggle = document.getElementById("translate_output");
  const languageRow = document.querySelector(".lang-options-row");
  if (translateToggle && languageRow) {
    toggleBlock(languageRow, translateToggle.checked);
    translateToggle.addEventListener("change", () =>
      toggleBlock(languageRow, translateToggle.checked)
    );
  }

  const maxTokensToggle = document.getElementById("set_max_new_tokens");
  const maxTokensRow = document.getElementById("max_new_tokens_row");
  if (maxTokensToggle && maxTokensRow) {
    toggleBlock(maxTokensRow, maxTokensToggle.checked);
    maxTokensToggle.addEventListener("change", () =>
      toggleBlock(maxTokensRow, maxTokensToggle.checked)
    );
  }
}

/* ------------------------------------------------------- busy form states */
function initFormBusyStates(root = document) {
  function busyButtonFor(event) {
    if (event.submitter) return event.submitter;
    const form = event.target;
    return form.querySelector("button[type='submit'], button:not([type])");
  }

  root.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      // Buttons can live outside the form (linked via the form attribute),
      // so resolve the actually submitted control first.
      const button = busyButtonFor(event);
      if (!button || button.dataset.busy === "true") return;

      button.dataset.busy = "true";
      button.dataset.originalLabel = button.innerHTML;
      button.disabled = true;

      const label = button.dataset.loadingLabel || t("working", {}, "Working…");
      button.innerHTML = `<span class="spinner" aria-hidden="true"></span>${label}`;

      const progress = document.getElementById("upload-progress");
      if (progress) {
        progress.classList.remove("hidden");
        progress.classList.add("progress--indeterminate");
      }

      // Keep the UI responsive: re-enable the button if the browser restores
      // the page from the back/forward cache.
      window.addEventListener("pageshow", () => {
        button.disabled = false;
        if (button.dataset.originalLabel) button.innerHTML = button.dataset.originalLabel;
        button.dataset.busy = "false";
        if (progress) progress.classList.add("hidden");
      }, { once: true });
    });
  });
}

/* -------------------------------------------- generative answer (async) */
// The search page is rendered as soon as the results are known; the answer
// card ([data-generate]) then asks /search/generate for the model answer and
// is replaced with it, the rating form goes to [data-feedback-slot].
function fragmentFrom(html) {
  const template = document.createElement("template");
  template.innerHTML = html || "";
  return template.content;
}

function initGenerativeAnswer() {
  const card = document.querySelector("[data-generate]");
  if (!card) return;

  const timer = card.querySelector("[data-gen-timer]");
  const started = Date.now();
  const tick = () => {
    if (timer) timer.textContent = t("seconds", { n: Math.floor((Date.now() - started) / 1000) }, "{n} s");
  };
  tick();
  const interval = window.setInterval(tick, 1000);

  const showFailure = () => {
    card.classList.remove("answer-card--pending");
    card.classList.add("answer-card--error");
    card.setAttribute("aria-busy", "false");
    card.querySelectorAll(".answer-skeleton, .answer-card__hint, .badge--live").forEach((node) => node.remove());
    const alert = document.createElement("div");
    alert.className = "alert alert-error";
    alert.setAttribute("role", "alert");
    alert.textContent = t("answer_failed", {}, "Could not load the generated answer.");
    card.append(alert);
  };

  const body = new FormData();
  body.append("generation_id", card.dataset.generate);

  fetch("/search/generate", { method: "POST", body, credentials: "same-origin" })
    .then((response) => response.json().catch(() => ({})))
    .then((payload) => {
      window.clearInterval(interval);
      if (!payload.answer_html) {
        showFailure();
        return;
      }
      const answer = fragmentFrom(payload.answer_html).firstElementChild;
      if (!answer) {
        showFailure();
        return;
      }
      answer.classList.add("is-arrived");
      card.replaceWith(answer);
      initCopyButtons(answer);

      const slot = document.querySelector("[data-feedback-slot]");
      if (slot && payload.feedback_html) {
        slot.replaceChildren(fragmentFrom(payload.feedback_html));
        initFormBusyStates(slot);
      }
    })
    .catch(() => {
      window.clearInterval(interval);
      showFailure();
    });
}

/* ---------------------------------------------------------------- init */
document.addEventListener("DOMContentLoaded", () => {
  initThemeToggle();
  initNavToggle();
  initTabs();
  initSliders();
  initFileSummary();
  initDropzone();
  initChunkPreview();
  initExamples();
  initConditionalFields();
  initFormBusyStates();
  initClamps();
  initScoreBars();
  initViewSwitches();
  initHitFilters();
  initHitExpanders();
  initHighlights();
  initCopyButtons();
  initGenerativeAnswer();
});

/* ------------------------- refresh category/document filters on demand */
function fillSelect(element, values) {
  if (!element) return;
  element.innerHTML = "";
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    element.appendChild(option);
  });
}

document.addEventListener("change", async (event) => {
  const select = event.target;
  if (!select.matches("select[name='collection_name']")) return;

  const scope = select.closest("form") || document;
  const targets = {
    categories: scope.querySelector("select[name='categories']"),
    documents: scope.querySelector("select[name='documents']"),
  };

  try {
    const response = await fetch(`/api/options?collection_name=${encodeURIComponent(select.value)}`);
    if (!response.ok) return;
    const payload = await response.json();
    if (!payload.status) return;

    Object.entries(targets).forEach(([key, element]) => {
      const values = payload.body[key] || [];
      fillSelect(element, values);
      const counter = scope.querySelector(`[data-count-for='${key}']`);
      if (counter) counter.textContent = values.length;
    });
  } catch (error) {
    console.error("Cannot refresh collection filters", error);
  }
});
