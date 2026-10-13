document.addEventListener("DOMContentLoaded", () => {
  // Tabs
  document.querySelectorAll("[data-tabs]").forEach((tabBar) => {
    tabBar.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", () => {
        const scope = tabBar.dataset.tabs;
        document
          .querySelectorAll(`[data-tab-group="${scope}"] button`)
          .forEach((b) => b.classList.remove("active"));
        document
          .querySelectorAll(`[data-tab-group="${scope}"] .tab-pane`)
          .forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        const pane = document.querySelector(`[data-tab-id="${btn.dataset.target}"]`);
        if (pane) pane.classList.add("active");
      });
    });
  });

  // Sliders: sync range input with the number input
  document.querySelectorAll("input[type='range'][data-pair]").forEach((range) => {
    const pair = document.querySelector(range.dataset.pair);
    if (!pair) return;
    const update = () => { pair.value = range.value; };
    range.addEventListener("input", update);
    pair.addEventListener("change", () => {
      range.value = pair.value;
      update();
    });
    update();
  });

  // Conditional form parts:
  // - generative QA block (model, percentage rank, doc names, translation, generation options)
  // - extractive QA / factored results toggles
  const genToggle = document.getElementById("use_qa_generative");
  const genBlock = document.getElementById("generative-qa-block");
  if (genToggle && genBlock) {
    genBlock.classList.toggle("hidden", !genToggle.checked);
    genToggle.addEventListener("change", () =>
      genBlock.classList.toggle("hidden", !genToggle.checked)
    );
  }

  const translateToggle = document.getElementById("translate_output");
  const langRow = document.querySelector(".lang-options-row");
  if (translateToggle && langRow) {
    langRow.classList.toggle("hidden", !translateToggle.checked);
    translateToggle.addEventListener("change", () =>
      langRow.classList.toggle("hidden", !translateToggle.checked)
    );
  }

  const setMaxTokens = document.getElementById("set_max_new_tokens");
  const maxTokensRow = document.getElementById("max_new_tokens_row");
  if (setMaxTokens && maxTokensRow) {
    maxTokensRow.classList.toggle("hidden", !setMaxTokens.checked);
    setMaxTokens.addEventListener("change", () =>
      maxTokensRow.classList.toggle("hidden", !setMaxTokens.checked)
    );
  }

  // Chat autoscroll
  const chatLog = document.getElementById("chat-log");
  if (chatLog) chatLog.scrollTop = chatLog.scrollHeight;
});

// Refresh category/document filters when another collection is selected
// (the Streamlit app re-ran the whole page after a collection was chosen).
document.addEventListener("change", async (event) => {
  const select = event.target;
  if (!select.matches("select[name='collection_name']")) return;

  const form = select.closest("form") || document;
  const targets = {
    categories: form.querySelector("select[name='categories']"),
    documents: form.querySelector("select[name='documents']"),
  };

  try {
    const response = await fetch(`/api/options?collection_name=${encodeURIComponent(select.value)}`);
    if (!response.ok) return;
    const payload = await response.json();
    if (!payload.status) return;

    Object.entries(targets).forEach(([key, element]) => {
      if (!element) return;
      const values = payload.body[key] || [];
      element.innerHTML = "";
      values.forEach((value) => {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        element.appendChild(option);
      });
      const counter = element.parentElement.querySelector(`[data-count-for='${key}']`);
      if (counter) counter.textContent = values.length;
    });
  } catch (error) {
    console.error("Cannot refresh collection filters", error);
  }
});
