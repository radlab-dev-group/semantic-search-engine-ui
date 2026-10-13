/* Semantic Search Engine UI — client side behaviour
   Theme, navigation, tabs, sliders, conditional form fields, collection
   filters, form busy states. No framework, no build step. */

const THEME_KEY = "sse-theme";
const THEME_ORDER = ["auto", "light", "dark"];

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
    button.setAttribute("title", `Theme: ${next} (click to change)`);
  });
  button.setAttribute("title", `Theme: ${document.documentElement.dataset.theme} (click to change)`);
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
function initScoreBars() {
  document.querySelectorAll("[data-score]").forEach((bar) => {
    const value = Number(bar.dataset.score);
    if (!Number.isFinite(value)) return;
    const ratio = value > 1 ? value / 100 : value;
    bar.style.setProperty("--score", `${Math.max(0, Math.min(1, ratio)) * 100}%`);
  });
}

/* ---------------------------------------------------------- copy buttons */
function initCopyButtons() {
  document.querySelectorAll("[data-copy]").forEach((button) => {
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
      button.textContent = "Copied";
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
      summary.textContent = "No files selected yet.";
      return;
    }

    const bytes = files.reduce((total, file) => total + file.size, 0);
    const size = bytes > 1048576
      ? `${(bytes / 1048576).toFixed(1)} MB`
      : `${Math.max(1, Math.round(bytes / 1024))} KB`;
    summary.textContent = `${files.length} file(s) selected · ${size}`;
  };

  fileInput.addEventListener("change", render);
  render();
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
function initFormBusyStates() {
  function busyButtonFor(event) {
    if (event.submitter) return event.submitter;
    const form = event.target;
    return form.querySelector("button[type='submit'], button:not([type])");
  }

  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", (event) => {
      // Buttons can live outside the form (linked via the form attribute),
      // so resolve the actually submitted control first.
      const button = busyButtonFor(event);
      if (!button || button.dataset.busy === "true") return;

      button.dataset.busy = "true";
      button.dataset.originalLabel = button.innerHTML;
      button.disabled = true;

      const label = button.dataset.loadingLabel || "Working…";
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

/* ---------------------------------------------------------------- init */
document.addEventListener("DOMContentLoaded", () => {
  initThemeToggle();
  initNavToggle();
  initTabs();
  initSliders();
  initFileSummary();
  initConditionalFields();
  initFormBusyStates();
  initClamps();
  initScoreBars();
  initCopyButtons();
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
