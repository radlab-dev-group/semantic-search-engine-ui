/* Semantic Search Engine UI — client side behaviour
   Theme, navigation, tabs, sliders, conditional form fields, collection
   filters, form busy states. No framework, no build step. */

const THEME_KEY = "sse-theme";
const THEME_ORDER = ["auto", "light", "dark"];

/* ------------------------------------------------------------------ theme */
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
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
function initTabs() {
  document.querySelectorAll("[data-tabs]").forEach((tabBar) => {
    tabBar.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        const scope = tabBar.dataset.tabs;
        document.querySelectorAll(`[data-tab-group="${scope}"] button`).forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(`[data-tab-group="${scope}"] .tab-pane`).forEach((pane) => pane.classList.remove("active"));
        btn.classList.add("active");
        const pane = document.querySelector(`[data-tab-id="${btn.dataset.target}"]`);
        if (pane) pane.classList.add("active");
      });
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
  document.querySelectorAll("form").forEach((form) => {
    form.addEventListener("submit", () => {
      const button = form.querySelector("button[type='submit'], button:not([type])");
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

/* ------------------------------------------------------------ chat log */
function initChatLog() {
  const chatLog = document.getElementById("chat-log");
  if (!chatLog) return;
  chatLog.scrollTop = chatLog.scrollHeight;

  // Ctrl/Cmd + Enter sends the message.
  const message = document.getElementById("message");
  let form = null;
  if (message) {
    // The textarea may live outside the <form> (linked with the form attribute).
    form = message.form instanceof HTMLFormElement
      ? message.form
      : document.getElementById(message.form);
  }
  if (message && form) {
    message.addEventListener("keydown", (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
        event.preventDefault();
        form.requestSubmit();
      }
    });
  }
}

/* ---------------------------------------------------------------- init */
document.addEventListener("DOMContentLoaded", () => {
  initThemeToggle();
  initNavToggle();
  initTabs();
  initSliders();
  initConditionalFields();
  initFormBusyStates();
  initChatLog();
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
