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

/* ------------------------- results: Markdown / context switches (toolbar) */
// [data-hits-toggle="markdown"] switches the passages between rendered
// Markdown and plain text, [data-hits-toggle="context"] shows / hides the
// left and right context. Both choices are remembered.
function initHitsToggles() {
  document.querySelectorAll("[data-hits-switches]").forEach((group) => {
    const root = group.closest("[data-view-switch]") || document;
    const list = root.querySelector("[data-hits]");
    if (!list) return;
    const classes = { markdown: "is-plain", context: "no-context" };

    group.querySelectorAll("[data-hits-toggle]").forEach((input) => {
      const name = input.dataset.hitsToggle;
      const key = `sse-hits-${name}`;
      const apply = () => list.classList.toggle(classes[name], !input.checked);
      try {
        const saved = localStorage.getItem(key);
        if (saved !== null) input.checked = saved === "on";
      } catch (error) {
        /* storage unavailable */
      }
      apply();
      input.addEventListener("change", () => {
        apply();
        try {
          localStorage.setItem(key, input.checked ? "on" : "off");
        } catch (error) {
          /* storage unavailable */
        }
      });
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
      if (output) {
        output.textContent = `${range.value}${output.dataset.suffix || ""}`;
        // Values that differ from the default are marked (search params)
        const fallback = range.dataset.default;
        const changed = fallback !== undefined && Number(fallback) !== Number(range.value);
        output.classList.toggle("is-changed", changed);
        output.title = changed ? t("changed_title", { value: fallback }, "Default: {value}") : "";
      }
      paintRange(range);
    };
    range.addEventListener("input", sync);
    sync();
  });
}

/* ------------------------------------------------------- search params */
// Number stepper (− / +) and preset chips of "number of results".
function initSteppers(root) {
  root.querySelectorAll("[data-stepper]").forEach((stepper) => {
    const input = stepper.querySelector("input[type='number']");
    if (!input) return;
    const clamp = (value) => {
      const min = Number(input.min || 1);
      const max = Number(input.max || 100);
      return Math.min(max, Math.max(min, Math.round(value)));
    };
    stepper.querySelectorAll("[data-step]").forEach((button) => {
      button.addEventListener("click", () => {
        input.value = clamp((Number(input.value) || 0) + Number(button.dataset.step));
        input.dispatchEvent(new Event("input", { bubbles: true }));
      });
    });
  });

  const chips = Array.from(root.querySelectorAll("[data-preset]"));
  const syncChips = () => {
    chips.forEach((chip) => {
      const input = document.getElementById(chip.dataset.presetFor);
      const active = input && Number(input.value) === Number(chip.dataset.preset);
      chip.classList.toggle("is-active", Boolean(active));
      chip.setAttribute("aria-pressed", active ? "true" : "false");
    });
  };
  chips.forEach((chip) => {
    chip.addEventListener("click", () => {
      const input = document.getElementById(chip.dataset.presetFor);
      if (!input) return;
      input.value = chip.dataset.preset;
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });
  root.addEventListener("input", syncChips);
  syncChips();
}

// A <select multiple> shown as a searchable list of toggles. The native
// select stays in the form (hidden) and remains the source of truth, so
// the submitted data and the collection refresh (fillSelect) are unchanged.
function initPicker(select) {
  const picker = document.createElement("div");
  picker.className = "picker";
  picker.innerHTML = `
    <div class="picker__bar">
      <input type="search" class="picker__search" autocomplete="off">
      <button type="button" class="picker__clear" hidden></button>
    </div>
    <div class="picker__list" role="group"></div>
    <p class="picker__status"></p>`;
  const bar = picker.querySelector(".picker__bar");
  const search = picker.querySelector(".picker__search");
  const clear = picker.querySelector(".picker__clear");
  const list = picker.querySelector(".picker__list");
  const status = picker.querySelector(".picker__status");
  search.placeholder = t("picker_search", {}, "Search…");
  search.setAttribute("aria-label", t("picker_search", {}, "Search…"));
  clear.textContent = t("picker_clear", {}, "Clear");

  const label = select.id ? document.querySelector(`label[for='${select.id}']`) : null;
  if (label) {
    label.id = `${select.id}-label`;
    list.setAttribute("aria-labelledby", label.id);
    // The native select is hidden: the label focuses the picker instead
    label.addEventListener("click", (event) => {
      event.preventDefault();
      (bar.hidden ? list.querySelector(".picker__opt") : search)?.focus();
    });
  }

  const updateStatus = () => {
    const options = Array.from(select.options);
    const chosen = options.filter((option) => option.selected).length;
    const query = search.value.trim();
    const visible = list.querySelectorAll(".picker__opt:not([hidden])").length;
    clear.hidden = chosen === 0;
    picker.classList.toggle("has-selection", chosen > 0);
    if (!options.length) {
      status.textContent = t("picker_empty", {}, "No items.");
    } else if (query && !visible) {
      status.textContent = t("picker_nomatch", { query }, "Nothing matches “{query}”.");
    } else if (chosen) {
      status.textContent = t("picker_selected", { n: chosen, total: options.length }, "{n} of {total} selected");
    } else {
      status.textContent = t("picker_all", { n: options.length }, "No filter ({n})");
    }
  };

  const filter = () => {
    const words = search.value.toLowerCase().split(/\s+/).filter(Boolean);
    list.querySelectorAll(".picker__opt").forEach((button) => {
      const text = button.dataset.value.toLowerCase();
      button.hidden = !words.every((word) => text.includes(word));
    });
    updateStatus();
  };

  const render = () => {
    list.replaceChildren();
    Array.from(select.options).forEach((option) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "picker__opt";
      button.dataset.value = option.value;
      button.setAttribute("aria-pressed", option.selected ? "true" : "false");
      button.title = option.value;

      const check = document.createElement("span");
      check.className = "picker__check";
      check.setAttribute("aria-hidden", "true");
      const text = document.createElement("span");
      text.className = "picker__label";
      // "pl/01-context": the parent path is dimmed, the last part stands out
      const cut = option.value.lastIndexOf("/");
      if (cut > 0 && cut < option.value.length - 1) {
        const parent = document.createElement("span");
        parent.className = "picker__parent";
        parent.textContent = option.value.slice(0, cut + 1);
        text.append(parent, option.value.slice(cut + 1));
      } else {
        text.textContent = option.textContent;
      }
      button.append(check, text);

      button.addEventListener("click", () => {
        option.selected = !option.selected;
        button.setAttribute("aria-pressed", option.selected ? "true" : "false");
        select.dispatchEvent(new Event("change", { bubbles: true }));
        updateStatus();
      });
      list.appendChild(button);
    });
    bar.hidden = select.options.length <= 6;
    filter();
  };

  search.addEventListener("input", filter);
  // The picker is inside the search form: Enter must not run a search
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") event.preventDefault();
    if (event.key === "Escape" && search.value) {
      event.preventDefault();
      search.value = "";
      filter();
    }
  });
  clear.addEventListener("click", () => {
    Array.from(select.options).forEach((option) => {
      option.selected = false;
    });
    render();
    select.dispatchEvent(new Event("change", { bubbles: true }));
  });
  select.addEventListener("picker:refresh", () => {
    search.value = "";
    render();
  });

  select.classList.add("picker-native");
  select.tabIndex = -1;
  select.setAttribute("aria-hidden", "true");
  select.after(picker);
  const hint = picker.nextElementSibling;
  if (hint && hint.matches("[data-picker-hint]")) hint.hidden = true;
  render();
}

// One-line summaries in the headers of the parameter groups.
function initGroupSummaries(panel) {
  const field = (name) => panel.querySelector(`[name='${name}']`);
  const isOn = (name) => {
    const input = field(name);
    if (!input) return false;
    return input.type === "checkbox" ? input.checked : Boolean(input.value);
  };
  const chosen = (name) => {
    const select = field(name);
    return select ? Array.from(select.selectedOptions).length : 0;
  };

  const summaries = {
    collection: () => {
      const collection = field("collection_name");
      const parts = [];
      const label = collection && collection.value && collection.selectedOptions
        ? (collection.selectedOptions[0]?.textContent || collection.value).trim()
        : "";
      parts.push(label || t("sum_no_collection", {}, "no collection"));
      const count = Number(field("results_count")?.value) || 0;
      parts.push(t("sum_results", { n: count }, "{n} results"));
      if (isOn("hybrid_search")) {
        parts.push(t("sum_hybrid", {}, "hybrid"));
      } else {
        parts.push(t("sum_vector_only", {}, "vector only"));
      }
      if (isOn("rerank_results")) parts.push(t("sum_rerank", {}, "reranking"));
      return parts.join(" · ");
    },
    models: () => {
      const parts = [];
      if (isOn("use_qa_generative")) {
        parts.push(t("sum_generative", {}, "generative QA"));
        const model = field("qa_gen_model");
        if (model && model.value) parts.push(model.value.split("/").pop());
      }
      if (isOn("use_qa_extractive")) parts.push(t("sum_extractive", {}, "extractive QA"));
      return parts.length ? parts.join(" · ") : t("sum_search_only", {}, "search only");
    },
    filters: () => {
      const parts = [];
      const categories = chosen("categories");
      const documents = chosen("documents");
      if (categories) parts.push(t("sum_categories", { n: categories }, "{n} categories"));
      if (documents) parts.push(t("sum_documents", { n: documents }, "{n} documents"));
      return parts.length ? parts.join(" · ") : t("sum_no_filters", {}, "no filters");
    },
  };

  const tuning = panel.querySelector(".expander--tune");
  const update = () => {
    panel.querySelectorAll("[data-group]").forEach((group) => {
      const target = group.querySelector("[data-group-summary]");
      const summary = summaries[group.dataset.group];
      if (target && summary) target.textContent = summary();
    });
    const group = panel.querySelector("[data-group='filters']");
    if (group) group.classList.toggle("is-active", chosen("categories") + chosen("documents") > 0);

    // Number of generation options that differ from their defaults
    if (tuning) {
      const counter = tuning.querySelector("[data-changed-count]");
      const changed = Array.from(tuning.querySelectorAll("input[type='range'][data-default]"))
        .filter((range) => !range.closest(".hidden"))
        .filter((range) => Number(range.value) !== Number(range.dataset.default)).length;
      if (counter) {
        counter.hidden = changed === 0;
        counter.textContent = t("sum_changed", { n: changed }, "changed: {n}");
      }
    }
  };
  panel.addEventListener("input", update);
  panel.addEventListener("change", update);
  update();
}

// The sidebar remembers itself in the browser: the values of its fields and
// which groups are folded survive leaving the page and coming back, also
// without running a search (the server only keeps the options of the last
// one). Runs before the other initialisers so that they see the restored
// state.
const PARAMS_KEY = "sse-search-params";
// Fields whose options belong to a collection: kept only for that collection
const COLLECTION_FIELDS = ["categories", "documents"];

function readParamsMemory() {
  try {
    const data = JSON.parse(localStorage.getItem(PARAMS_KEY));
    return data && typeof data === "object" ? data : null;
  } catch (error) {
    return null;
  }
}

function writeParamsMemory(data) {
  try {
    if (data) localStorage.setItem(PARAMS_KEY, JSON.stringify(data));
    else localStorage.removeItem(PARAMS_KEY);
  } catch (error) {
    /* storage unavailable */
  }
}

function paramsFields(panel) {
  return Array.from(panel.querySelectorAll("input[name], select[name]"))
    .filter((field) => field.type !== "hidden");
}

function paramsGroups(panel) {
  return Array.from(panel.querySelectorAll("details[data-group], details[data-remember]"));
}

function groupKey(group) {
  return group.dataset.remember || group.dataset.group;
}

function snapshotParams(panel) {
  const fields = {};
  paramsFields(panel).forEach((field) => {
    if (field.type === "checkbox") {
      fields[field.name] = field.checked;
    } else if (field.multiple) {
      fields[field.name] = Array.from(field.selectedOptions, (option) => option.value);
    } else {
      fields[field.name] = field.value;
    }
  });
  const open = {};
  paramsGroups(panel).forEach((group) => {
    open[groupKey(group)] = group.open;
  });
  return { fields, open };
}

function restoreParams(panel, memory, collectionFromUrl) {
  if (!memory) return;
  const fields = memory.fields || {};
  const open = memory.open || {};

  paramsGroups(panel).forEach((group) => {
    const saved = open[groupKey(group)];
    if (typeof saved === "boolean") group.open = saved;
  });

  const hasOption = (select, value) =>
    Array.from(select.options).some((option) => option.value === String(value));

  // A collection named in the address (e.g. "Search" on a collection card)
  // wins over the remembered one
  const collection = panel.querySelector("select[name='collection_name']");
  let switched = false;
  if (
    collection
    && !collectionFromUrl
    && typeof fields.collection_name === "string"
    && fields.collection_name
    && fields.collection_name !== collection.value
    && hasOption(collection, fields.collection_name)
  ) {
    collection.value = fields.collection_name;
    switched = true;
  }

  const applyField = (field) => {
    const saved = fields[field.name];
    if (saved === undefined) return;
    if (field.type === "checkbox") {
      field.checked = Boolean(saved);
    } else if (field.multiple) {
      const wanted = new Set(Array.isArray(saved) ? saved : []);
      Array.from(field.options).forEach((option) => {
        option.selected = wanted.has(option.value);
      });
    } else if (field.tagName === "SELECT") {
      if (hasOption(field, saved)) field.value = String(saved);
    } else if (typeof saved === "string" || typeof saved === "number") {
      field.value = String(saved);
    }
  };

  const filtersBelongHere = Boolean(collection) && fields.collection_name === collection.value;
  paramsFields(panel).forEach((field) => {
    if (field.name === "collection_name") return;
    if (!COLLECTION_FIELDS.includes(field.name)) {
      applyField(field);
    } else if (switched) {
      // The options of the other collection arrive with fillSelect
      field.addEventListener("picker:refresh", () => applyField(field), { once: true });
    } else if (filtersBelongHere) {
      applyField(field);
    }
  });

  // Loads the filters and the history of the remembered collection
  if (switched) collection.dispatchEvent(new Event("change", { bubbles: true }));
}

function initParamsMemory() {
  const panel = document.querySelector("[data-params]");
  if (!panel) return;
  const url = new URL(window.location.href);
  const save = () => writeParamsMemory(snapshotParams(panel));

  if (url.searchParams.has("params_reset")) {
    // "Restore defaults": the server forgot its copy, forget ours too; the
    // marker is dropped so that a refresh does not reset the sidebar again
    writeParamsMemory(null);
    url.searchParams.delete("params_reset");
    window.history.replaceState(window.history.state, "", url);
  } else {
    restoreParams(panel, readParamsMemory(), url.searchParams.has("collection_name"));
  }

  panel.addEventListener("input", save);
  panel.addEventListener("change", save);
  paramsGroups(panel).forEach((group) => group.addEventListener("toggle", save));
  save();
}

function initParamsPanel() {
  document.querySelectorAll("[data-params]").forEach((panel) => {
    initSteppers(panel);
    panel.querySelectorAll("select[data-picker]").forEach(initPicker);
    initGroupSummaries(panel);
  });
}

/* -------------------------------------------- query console: collection */
// The banner above the question shows which collection it goes to: the name,
// the description and the date come from the data-* attributes of the chosen
// <option>, the number of documents from the "documents" filter.
function updateCollectionBanner(select, documentsCount = null) {
  const banner = document.querySelector("[data-collection-banner]");
  if (!banner) return;
  const option = select && select.value ? select.selectedOptions[0] : null;
  banner.classList.toggle("is-empty", !option);

  const manage = banner.querySelector("[data-banner-manage]");
  if (manage) {
    manage.href = option
      ? `/collections/manage?collection_name=${encodeURIComponent(option.value)}`
      : "/collections/manage";
  }
  if (!option) return;

  const label = (option.textContent || option.value).trim();
  const name = banner.querySelector("[data-banner-name]");
  if (name) {
    name.textContent = label;
    name.title = label;
  }
  const id = banner.querySelector("[data-banner-id]");
  if (id) {
    id.textContent = option.value;
    id.title = option.value;
    id.hidden = option.value === label;
  }

  const description = (option.dataset.description || "").trim();
  const desc = banner.querySelector("[data-banner-desc]");
  if (desc) {
    desc.textContent = description || t("banner_no_description", {}, "No description");
    desc.classList.toggle("is-muted", !description);
    if (description) desc.title = description;
    else desc.removeAttribute("title");
  }

  const created = (option.dataset.created || "").trim();
  const dateWrap = banner.querySelector("[data-banner-date-wrap]");
  const date = banner.querySelector("[data-banner-date]");
  if (dateWrap) dateWrap.hidden = !created;
  if (date) date.textContent = created ? t("banner_created", { date: created }, "Created {date}") : "";

  if (documentsCount !== null) {
    const docs = banner.querySelector("[data-banner-docs]");
    if (docs) docs.textContent = t("sum_documents", { n: documentsCount }, "{n} documents");
  }
}

function initCollectionBanner() {
  const banner = document.querySelector("[data-collection-banner]");
  if (!banner) return;
  const select = document.querySelector("[data-params] select[name='collection_name']");
  // The remembered collection may differ from the one the server rendered
  updateCollectionBanner(select);

  const change = banner.querySelector("[data-banner-change]");
  if (change && select) {
    change.addEventListener("click", () => {
      const group = select.closest("details");
      if (group) group.open = true;
      select.scrollIntoView({ behavior: "smooth", block: "center" });
      select.focus({ preventScroll: true });
    });
  }
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
// One preview per form ("Upload files" and "Paste text" each have their own)
function initChunkPreview() {
  document.querySelectorAll("[data-chunk-preview]").forEach((preview) => {
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
  });
}

/* ------------------------------------------- new collection: chunking */
// The chunk size of a new collection is capped by max_model_length of the
// chosen embedder (data-max-length of the <option>, empty = no known limit);
// the overlap has to stay within [0, chunk). A chunk which does not fit the
// reranker is only reported (the query shares that budget), never blocked.
// Any edit of the two fields flags "chunking_edited", so that the server
// sends "chunking" to the engine only when the defaults were touched.
function modelOption(select) {
  return select && select.value ? select.selectedOptions[0] : null;
}

function modelLimit(select) {
  const option = modelOption(select);
  const limit = option ? Number(option.dataset.maxLength) : NaN;
  return option && option.dataset.maxLength !== "" && Number.isFinite(limit) && limit > 0
    ? limit
    : null;
}

function describeModel(select, target) {
  if (!target) return;
  const option = modelOption(select);
  if (!option) {
    target.textContent = "";
    return;
  }
  const parts = [];
  if (option.dataset.vectorSize) {
    parts.push(t("model_vector", { n: option.dataset.vectorSize }, "vector {n}"));
  }
  const limit = modelLimit(select);
  parts.push(
    limit
      ? t("model_max_length", { n: limit }, "max input {n} tokens")
      : t("model_no_limit", {}, "no known length limit")
  );
  if (option.dataset.device) parts.push(option.dataset.device);
  target.textContent = parts.join(" · ");
}

function initCollectionChunking() {
  const form = document.querySelector("[data-collection-form]");
  if (!form) return;
  const embedder = form.querySelector("[data-model-select='embedder']");
  const reranker = form.querySelector("[data-model-select='reranker']");
  const chunk = form.querySelector("[data-chunk-size]");
  const overlap = form.querySelector("[data-chunk-overlap]");
  const edited = form.querySelector("[data-chunking-edited]");
  const chunkMsg = form.querySelector("[data-chunk-msg]");
  const overlapMsg = form.querySelector("[data-overlap-msg]");
  const rerankerMsg = form.querySelector("[data-reranker-msg]");
  const limitHint = form.querySelector("[data-chunk-limit]");
  const defaultHint = limitHint ? limitHint.textContent : "";
  if (!chunk || !overlap) return;

  const setInvalid = (field, message, note) => {
    field.classList.toggle("is-invalid", Boolean(message));
    if (message) field.setAttribute("aria-invalid", "true");
    else field.removeAttribute("aria-invalid");
    field.setCustomValidity(message || "");
    if (note) {
      note.textContent = message || "";
      note.hidden = !message;
    }
  };

  const validate = () => {
    const limit = modelLimit(embedder);
    const model = embedder ? (modelOption(embedder)?.textContent || "").trim() : "";
    // null = no ceiling: the attribute is dropped, not set to a magic number
    if (limit) chunk.max = String(limit);
    else chunk.removeAttribute("max");
    if (limitHint) {
      limitHint.textContent = limit
        ? t("chunk_limit_hint", { model, n: limit }, "Ceiling for the embedder {model}: {n} tokens.")
        : model
          ? t("chunk_no_limit_hint", { model }, "The embedder {model} reports no length limit — no ceiling.")
          : defaultHint;
    }

    const size = chunk.value === "" ? null : Number(chunk.value);
    const over = overlap.value === "" ? null : Number(overlap.value);

    let chunkError = "";
    if (size !== null && limit && size > limit) {
      chunkError = t("chunk_too_long", { n: limit, model }, "The chunk cannot exceed {n} tokens (max input of the embedder {model}).");
    } else if (size !== null && (!Number.isFinite(size) || size < 1)) {
      chunkError = t("chunk_size_error", {}, "The chunk size must be a whole number above 0.");
    }
    setInvalid(chunk, chunkError, chunkMsg);

    let overlapError = "";
    if (size !== null && size >= 1) {
      overlap.max = String(size - 1);
      if (over !== null && !(over >= 0 && over < size)) {
        overlapError = t("chunk_overlap_error", { n: size - 1 }, "The overlap must be a number from 0 to {n}.");
      }
    } else {
      overlap.removeAttribute("max");
      if (over !== null && over < 0) {
        overlapError = t("chunk_overlap_error", { n: 0 }, "The overlap must be a number from 0 to {n}.");
      }
    }
    setInvalid(overlap, overlapError, overlapMsg);

    // Soft warning only: a chunk at or above the reranker input is truncated
    // there, the engine still accepts it
    if (rerankerMsg) {
      const rerankLimit = modelLimit(reranker);
      const rerankModel = reranker ? (modelOption(reranker)?.textContent || "").trim() : "";
      const warn = size !== null && rerankLimit && size >= rerankLimit;
      rerankerMsg.hidden = !warn;
      rerankerMsg.textContent = warn
        ? t(
            "chunk_reranker_warning",
            { chunk: size, model: rerankModel, n: rerankLimit },
            "A chunk of {chunk} tokens does not fit the reranker {model} (limit {n} tokens)."
          )
        : "";
    }
  };

  const describe = () => {
    describeModel(embedder, form.querySelector("[data-model-info='embedder']"));
    describeModel(reranker, form.querySelector("[data-model-info='reranker']"));
  };

  [chunk, overlap].forEach((field) => {
    field.addEventListener("input", () => {
      if (edited) edited.value = "1";
      validate();
    });
  });
  [embedder, reranker].forEach((select) => {
    if (!select) return;
    select.addEventListener("change", () => {
      describe();
      validate();
    });
  });
  // Browser validation bubbles would hide the inline notes: keep both
  form.addEventListener("submit", (event) => {
    validate();
    if (!chunk.checkValidity() || !overlap.checkValidity()) {
      event.preventDefault();
      (chunk.checkValidity() ? overlap : chunk).focus();
    }
  });
  describe();
  validate();
}

/* ----------------------------------------------- indexing: chunking mode */
// "Collection settings" leaves the chunk keys out of indexing_options (the
// engine then uses what the collection declares); "custom" enables the
// sliders and sends both keys. On a strict collection the custom choice shows
// up front that the engine will answer with CHUNKING_MISMATCH.
function initChunkingMode() {
  document.querySelectorAll("[data-chunk-mode]").forEach((mode) => {
    const form = mode.closest("form") || document;
    const fields = form.querySelector("[data-chunk-fields]");
    const sliders = fields
      ? Array.from(fields.querySelectorAll("input[type='range']"))
      : [];
    const warning = mode.querySelector("[data-strict-warning]");
    const radios = Array.from(mode.querySelectorAll("input[name='chunking_mode']"));
    if (!radios.length) return;

    const reference = {
      max_tokens_in_chunk: mode.dataset.refChunk,
      number_of_overlap_tokens: mode.dataset.refOverlap,
    };

    const apply = () => {
      const custom = radios.some((radio) => radio.checked && radio.value === "custom");
      if (fields) fields.classList.toggle("is-locked", !custom);
      sliders.forEach((slider) => {
        slider.disabled = !custom;
        // Back to the collection settings: the sliders show them again
        if (!custom && reference[slider.name] !== undefined && reference[slider.name] !== "") {
          slider.value = reference[slider.name];
          slider.dispatchEvent(new Event("input", { bubbles: true }));
        }
      });
      if (warning) warning.hidden = !custom;
      // The refused value is no longer shown once the user changes the mode
      if (fields && !custom) {
        fields.querySelectorAll(".is-invalid").forEach((row) => row.classList.remove("is-invalid"));
        fields.querySelectorAll("[aria-invalid]").forEach((el) => el.removeAttribute("aria-invalid"));
        const note = fields.querySelector("[data-too-long-note]");
        if (note) note.hidden = true;
      }
    };
    radios.forEach((radio) => radio.addEventListener("change", apply));
    apply();
  });
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

  root.querySelectorAll("form:not([method='dialog'])").forEach((form) => {
    form.addEventListener("submit", (event) => {
      // Buttons can live outside the form (linked via the form attribute),
      // so resolve the actually submitted control first.
      const button = busyButtonFor(event);
      if (!button || button.dataset.busy === "true") return;

      // A disabled submitter is left out of the submitted data, so its
      // name/value (e.g. document_name of a row) goes in a hidden field.
      if (button.name && button.form === form) {
        const carrier = document.createElement("input");
        carrier.type = "hidden";
        carrier.name = button.name;
        carrier.value = button.value;
        carrier.dataset.submitterCopy = "";
        form.append(carrier);
        window.addEventListener("pageshow", () => carrier.remove(), { once: true });
      }

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

/* ------------------------------------------------ delete confirmations */
// Forms (or their submit buttons) with data-confirm open the styled dialog
// of base.html instead of submitting right away. Optional attributes, read
// from the button first and then from the form:
//   data-confirm-title, data-confirm-ok   - heading / label of the button
//   data-confirm-items                    - one name listed in the dialog
//   data-confirm-items-from="<field>"     - ids typed in a field of the form
//   data-confirm-phrase                   - text to type before confirming
function confirmAttr(name, submitter, form) {
  if (submitter && submitter.dataset[name] !== undefined) return submitter.dataset[name];
  return form.dataset[name];
}

function confirmItems(submitter, form) {
  if (submitter && submitter.matches("[data-doc-delete-selected]")) {
    return Array.from(form.querySelectorAll(".doc-checkbox:checked")).map((box) => box.value);
  }
  const single = confirmAttr("confirmItems", submitter, form);
  if (single) return [single];
  const fieldName = confirmAttr("confirmItemsFrom", submitter, form);
  const field = fieldName ? form.elements.namedItem(fieldName) : null;
  if (field && field.value) {
    return field.value.split(/[\s,]+/).filter((part) => /^\d+$/.test(part)).map((id) => `#${id}`);
  }
  return [];
}

function initConfirmDialogs() {
  const dialog = document.getElementById("confirm-dialog");
  if (!dialog) return;
  const title = dialog.querySelector(".confirm-dialog__title");
  const message = dialog.querySelector(".confirm-dialog__message");
  const list = dialog.querySelector("[data-confirm-list]");
  const phraseBox = dialog.querySelector("[data-confirm-phrase-box]");
  const phraseLabel = dialog.querySelector("[data-confirm-phrase-label]");
  const phraseInput = phraseBox.querySelector("input");
  const okButton = dialog.querySelector("[data-confirm-ok]");
  const warning = dialog.querySelector(".confirm-dialog__warning");
  const icon = dialog.querySelector(".confirm-dialog__icon");
  const defaults = {
    title: title.textContent,
    ok: okButton.textContent,
    iconHtml: icon ? icon.innerHTML : "",
  };
  const resetIconSvg = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>';
  const canShowModal = typeof dialog.showModal === "function";

  const resetDialogVisuals = () => {
    if (warning) warning.classList.remove("hidden");
    if (icon) icon.innerHTML = defaults.iconHtml;
  };

  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("a[data-confirm], button[data-confirm]:not([type=submit])");
    if (!trigger) return;
    const text = trigger.dataset.confirm;
    if (!text) return;

    event.preventDefault();
    event.stopImmediatePropagation();

    const phrase = trigger.dataset.confirmPhrase || "";
    const showWarning = trigger.dataset.confirmWarning !== "false";
    const iconType = trigger.dataset.confirmIcon;

    if (!canShowModal) {
      if (window.confirm(text)) {
        if (trigger.tagName === "A" && trigger.href) {
          window.location.href = trigger.href;
        }
      }
      return;
    }

    title.textContent = trigger.dataset.confirmTitle || defaults.title;
    okButton.textContent = trigger.dataset.confirmOk || defaults.ok;
    message.textContent = text;
    if (warning) warning.classList.toggle("hidden", !showWarning);
    if (icon) {
      icon.innerHTML = iconType === "reset" ? resetIconSvg : defaults.iconHtml;
    }

    list.replaceChildren();
    list.classList.add("hidden");

    phraseBox.classList.toggle("hidden", !phrase);
    phraseInput.value = "";
    okButton.disabled = Boolean(phrase);
    if (phrase) {
      phraseLabel.textContent = t("confirm_type", { phrase }, "Type {phrase} to confirm");
      phraseInput.oninput = () => {
        okButton.disabled = phraseInput.value.trim() !== phrase;
      };
    }

    dialog.onclose = () => {
      dialog.onclose = null;
      resetDialogVisuals();
      if (dialog.returnValue !== "ok") return;
      if (trigger.tagName === "A" && trigger.href) {
        window.location.href = trigger.href;
      }
    };
    dialog.returnValue = "";
    dialog.showModal();
    (phrase ? phraseInput : dialog.querySelector("[data-confirm-cancel]")).focus();
  });

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.method === "dialog") return;
    const submitter = event.submitter || null;
    const text = confirmAttr("confirm", submitter, form);
    if (text === undefined) return;
    if (form.dataset.confirmed === "true") {
      delete form.dataset.confirmed;
      return;
    }

    // Not confirmed yet: keep the other submit handlers (busy state) quiet
    event.preventDefault();
    event.stopImmediatePropagation();

    const items = confirmItems(submitter, form);
    let question = text;
    if (submitter && submitter.matches("[data-doc-delete-selected]")) {
      question = t("confirm_docs_selected", { n: items.length }, text);
    }
    const phrase = confirmAttr("confirmPhrase", submitter, form) || "";
    const showWarning = confirmAttr("confirmWarning", submitter, form) !== "false";
    const iconType = confirmAttr("confirmIcon", submitter, form);

    if (!canShowModal) {
      if (window.confirm(question)) {
        form.dataset.confirmed = "true";
        form.requestSubmit(submitter);
      }
      return;
    }

    title.textContent = confirmAttr("confirmTitle", submitter, form) || defaults.title;
    okButton.textContent = confirmAttr("confirmOk", submitter, form) || defaults.ok;
    message.textContent = question;
    if (warning) warning.classList.toggle("hidden", !showWarning);
    if (icon) {
      icon.innerHTML = iconType === "reset" ? resetIconSvg : defaults.iconHtml;
    }

    list.replaceChildren(...items.slice(0, 8).map((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      return li;
    }));
    if (items.length > 8) {
      const more = document.createElement("li");
      more.className = "confirm-dialog__more";
      more.textContent = t("confirm_more", { n: items.length - 8 }, "+{n} more");
      list.append(more);
    }
    list.classList.toggle("hidden", !items.length);

    phraseBox.classList.toggle("hidden", !phrase);
    phraseInput.value = "";
    okButton.disabled = Boolean(phrase);
    if (phrase) {
      phraseLabel.textContent = t("confirm_type", { phrase }, "Type {phrase} to confirm");
      phraseInput.oninput = () => {
        okButton.disabled = phraseInput.value.trim() !== phrase;
      };
    }

    dialog.onclose = () => {
      dialog.onclose = null;
      resetDialogVisuals();
      if (dialog.returnValue !== "ok") return;
      form.dataset.confirmed = "true";
      form.requestSubmit(submitter);
    };
    dialog.returnValue = "";
    dialog.showModal();
    (phrase ? phraseInput : dialog.querySelector("[data-confirm-cancel]")).focus();
  }, true);

  // A click on the backdrop cancels
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close("cancel");
  });
}

/* ------------------------------------------- knowledge base: documents */
function initDocList() {
  document.querySelectorAll("[data-doc-list]").forEach((form) => {
    const boxes = Array.from(form.querySelectorAll(".doc-checkbox"));
    const master = form.querySelector("[data-doc-master]");
    const filter = form.querySelector("[data-doc-filter]");
    const counter = form.querySelector("[data-doc-selected]");
    const button = form.querySelector("[data-doc-delete-selected]");
    const bulk = Array.from(form.querySelectorAll("[data-doc-bulk]"));
    const noMatch = form.querySelector("[data-doc-nomatch]");
    const visible = () => boxes.filter((box) => !box.closest(".doc-row").classList.contains("hidden"));

    const update = () => {
      const checked = boxes.filter((box) => box.checked).length;
      if (button) button.disabled = checked === 0;
      bulk.forEach((control) => { control.disabled = checked === 0; });
      if (counter) counter.textContent = checked ? t("docs_selected", { n: checked }, "{n} selected") : "";
      boxes.forEach((box) => box.closest(".doc-row").classList.toggle("is-selected", box.checked));
      if (master) {
        const shown = visible();
        const shownChecked = shown.filter((box) => box.checked).length;
        master.checked = shown.length > 0 && shownChecked === shown.length;
        master.indeterminate = shownChecked > 0 && shownChecked < shown.length;
      }
    };

    boxes.forEach((box) => box.addEventListener("change", update));
    if (master) {
      master.addEventListener("change", () => {
        visible().forEach((box) => { box.checked = master.checked; });
        update();
      });
    }
    if (filter) {
      filter.addEventListener("input", () => {
        const query = filter.value.toLowerCase().trim();
        let shown = 0;
        boxes.forEach((box) => {
          const row = box.closest(".doc-row");
          const match = !query || (row.dataset.name || "").includes(query);
          row.classList.toggle("hidden", !match);
          if (match) shown += 1;
        });
        if (noMatch) noMatch.classList.toggle("hidden", shown > 0);
        update();
      });
      // Enter in the filter must not submit the delete form
      filter.addEventListener("keydown", (event) => {
        if (event.key === "Enter") event.preventDefault();
      });
    }
    update();
  });
}

// "In search" switch of a document row: flips use_in_search of the document
// in the engine without reloading the page (the switch is a submit button of
// the list form, so without JS it posts the form to the same endpoint).
function setDocRowState(row, inSearch) {
  const toggle = row.querySelector("[data-doc-toggle]");
  row.classList.toggle("is-disabled", !inSearch);
  const badge = row.querySelector("[data-doc-state]");
  if (badge) badge.classList.toggle("hidden", inSearch);
  if (!toggle) return;
  toggle.setAttribute("aria-checked", String(inSearch));
  toggle.title = inSearch ? toggle.dataset.titleOn : toggle.dataset.titleOff;
  toggle.setAttribute(
    "formaction",
    `/collections/manage/visibility?use_in_search=${inSearch ? 0 : 1}`
  );
}

function initDocVisibility() {
  document.querySelectorAll("[data-doc-list]").forEach((form) => {
    const status = form.querySelector("[data-doc-visibility-status]");
    const badge = document.querySelector("[data-doc-disabled-badge]");
    const counter = document.querySelector("[data-doc-disabled-count]");

    const refreshCount = () => {
      const disabled = form.querySelectorAll(".doc-row.is-disabled").length;
      if (counter) counter.textContent = String(disabled);
      if (badge) badge.classList.toggle("hidden", disabled === 0);
    };
    const report = (text, isError) => {
      if (!status) return;
      status.textContent = text || "";
      status.classList.toggle("is-error", Boolean(isError));
    };

    form.querySelectorAll("[data-doc-toggle]").forEach((toggle) => {
      toggle.addEventListener("click", async (event) => {
        event.preventDefault();
        if (toggle.dataset.busy === "true") return;
        const row = toggle.closest(".doc-row");
        const wasOn = toggle.getAttribute("aria-checked") === "true";

        const data = new FormData();
        data.append("collection_name", form.elements.namedItem("collection_name").value);
        data.append("toggle_document", toggle.value);
        data.append("use_in_search", wasOn ? "0" : "1");

        toggle.dataset.busy = "true";
        toggle.classList.add("is-busy");
        setDocRowState(row, !wasOn);
        try {
          const response = await fetch("/collections/manage/visibility", {
            method: "POST",
            body: data,
            headers: { Accept: "application/json" },
            credentials: "same-origin",
          });
          const payload = await response.json().catch(() => ({}));
          if (response.status === 401) {
            window.location.href = "/login";
            return;
          }
          if (!response.ok || !payload.status) throw new Error(payload.error || "");
          const changed = (payload.documents || []).includes(toggle.value);
          setDocRowState(row, changed ? Boolean(payload.use_in_search) : wasOn);
          report(payload.message, !changed);
        } catch (error) {
          setDocRowState(row, wasOn);
          report(error.message || t("visibility_failed", {}, "Could not change the document"), true);
        } finally {
          toggle.dataset.busy = "false";
          toggle.classList.remove("is-busy");
          refreshCount();
        }
      });
    });
  });
}

/* ----------------------------------------------- small page behaviours */
function initAutosubmit() {
  document.querySelectorAll("form[data-autosubmit]").forEach((form) => {
    form.querySelectorAll("select").forEach((select) => {
      select.addEventListener("change", () => form.requestSubmit());
    });
  });
}

function initDismiss() {
  document.querySelectorAll("[data-dismiss]").forEach((button) => {
    button.addEventListener("click", () => {
      const alert = button.closest(".alert");
      if (alert) alert.remove();
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

/* ------------------------------------------------------ search history */
// Client-side filter of the history panel (the list is short, max. 50).
function initHistory(root = document) {
  root.querySelectorAll("[data-history]").forEach((panel) => {
    const input = panel.querySelector("[data-history-filter]");
    if (!input) return;
    const items = Array.from(panel.querySelectorAll("[data-history-item]"));
    const nomatch = panel.querySelector("[data-history-nomatch]");

    input.addEventListener("input", () => {
      const words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      let visible = 0;
      items.forEach((item) => {
        const show = words.every((word) => item.dataset.query.includes(word));
        item.hidden = !show;
        if (show) visible += 1;
      });
      if (nomatch) nomatch.hidden = visible > 0;
    });
    // The panel is inside the search form: Enter must not run a search
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") event.preventDefault();
    });
  });
}

// Another collection chosen in the sidebar: show its history.
async function refreshHistory(collectionName, collectionLabel = "") {
  const panel = document.querySelector("[data-history]");
  if (!panel) return;
  const query = new URLSearchParams({ collection_name: collectionName, collection_label: collectionLabel });
  try {
    const response = await fetch(`/search/history?${query}`, {
      credentials: "same-origin",
    });
    if (!response.ok) return;
    const payload = await response.json();
    const fresh = fragmentFrom(payload.html).firstElementChild;
    if (!fresh) return;
    const box = panel.querySelector("[data-history-box]");
    const freshBox = fresh.querySelector("[data-history-box]");
    if (box && freshBox) freshBox.open = box.open;
    panel.replaceWith(fresh);
    initHistory(fresh.parentElement);
  } catch (error) {
    console.error("Cannot refresh the search history", error);
  }
}

/* ---------------------------------------------------------------- init */
document.addEventListener("DOMContentLoaded", () => {
  initThemeToggle();
  initNavToggle();
  initTabs();
  initParamsMemory();
  initSliders();
  initParamsPanel();
  initCollectionBanner();
  initFileSummary();
  initDropzone();
  initChunkPreview();
  initChunkingMode();
  initCollectionChunking();
  initExamples();
  initConditionalFields();
  initFormBusyStates();
  initClamps();
  initScoreBars();
  initViewSwitches();
  initHitFilters();
  initHitExpanders();
  initHitsToggles();
  initHighlights();
  initCopyButtons();
  initGenerativeAnswer();
  initHistory();
  initConfirmDialogs();
  initDocList();
  initDocVisibility();
  initAutosubmit();
  initDismiss();
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
  element.dispatchEvent(new Event("picker:refresh"));
  element.dispatchEvent(new Event("change", { bubbles: true }));
}

document.addEventListener("change", async (event) => {
  const select = event.target;
  if (!select.matches("select[name='collection_name']")) return;
  // The knowledge base switcher reloads the page with the other collection
  if (select.closest("form[data-autosubmit]")) return;

  const scope = select.closest("form") || document;
  refreshHistory(select.value, (select.selectedOptions[0]?.textContent || "").trim());
  updateCollectionBanner(select);
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
    updateCollectionBanner(select, (payload.body.documents || []).length);
  } catch (error) {
    console.error("Cannot refresh collection filters", error);
  }
});
