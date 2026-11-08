/* RAG chat for employees – the browser interface.
   Calls only the frontend server's /ui-api/*; the frontend calls the RadLab backend (map in the README). */
(() => {
  "use strict";

  const DATA = JSON.parse(document.getElementById("app-data").textContent);
  const CFG = DATA.config;
  const T = DATA.t;
  const $ = (s, el = document) => el.querySelector(s);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const t = (key, vars = {}) => Object.entries(vars).reduce((s, [k, v]) => s.split(`{${k}}`).join(v), T[key] ?? key);
  const icon = (id, cls = "icon") => `<svg class="${cls}" aria-hidden="true"><use href="#i-${id}"/></svg>`;
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : v; } catch { return d; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch { /* private window */ } },
  };
  const docsWord = (n) => {
    if (n === 1) return t("word.document.one");
    const d = n % 10, h = n % 100;
    return d >= 2 && d <= 4 && (h < 10 || h >= 20) ? t("word.document.few") : t("word.document.many");
  };
  const fmtById = (id) => CFG.formats.find((f) => f.id === id) || CFG.formats[0];
  const seconds = (v) => (typeof v === "number" ? `${v.toFixed(1)} s` : "");

  const state = {
    collections: [],
    baseName: null,            // null = conversation base unknown (resumed chat without metadata)
    docs: {},                  // base -> [{name, stem, filetype}]
    selected: {},              // base -> Set of names
    chatId: null,
    messages: [],
    chats: [],
    showAllChats: false,
    panel: store.get("rag-panel", "docs") === "closed" ? null : "docs",
    docFilter: "",
    doc: null,
    popover: false,
    format: store.get("rag-format", CFG.defaultFormat),
    waiting: null,
    offline: false,
    noAccess: false,
    loading: true,
  };
  if (!CFG.formats.some((f) => f.id === state.format)) state.format = CFG.defaultFormat;

  const base = () => state.collections.find((c) => c.name === state.baseName) || null;
  const docs = () => state.docs[state.baseName] || [];
  const sel = () => state.selected[state.baseName] || new Set();
  const allSelected = () => sel().size === docs().length;

  /* ---------- Communication with the frontend server ---------- */
  async function api(path, opts = {}) {
    let res;
    try {
      res = await fetch(path, {
        method: opts.method || "GET",
        headers: opts.body ? { "Content-Type": "application/json" } : {},
        body: opts.body ? JSON.stringify(opts.body) : undefined,
        signal: opts.signal,
        credentials: "same-origin",
      });
    } catch (err) {
      if (err.name === "AbortError") return { ok: false, error: "aborted" };
      return { ok: false, error: "unavailable" };
    }
    let data = null;
    try { data = await res.json(); } catch { /* empty response */ }
    if (res.status === 401) { sessionExpired(); return { ok: false, error: "auth" }; }
    if (!res.ok) return { ok: false, status: res.status, error: (data && data.error) || "backend", message: data && data.message };
    return { ok: true, data };
  }

  /* ---------- Render ---------- */
  function render(scrollFeed = false) {
    const root = $("#root");
    root.removeAttribute("aria-busy");
    const cls = ["app"];
    if (!state.panel || state.noAccess) cls.push("panel-closed");
    if (state.panel === "doc") cls.push("reading");
    const keep = $("#q") ? { value: $("#q").value, focus: document.activeElement === $("#q") } : null;
    const prevFeed = $(".feed");
    const prevHistory = $(".history");
    const prevPanel = $(".panel-body");
    const prevPopover = $(".popover-list");
    const feedTop = prevFeed ? prevFeed.scrollTop : null;
    const historyTop = prevHistory ? prevHistory.scrollTop : null;
    const panelTop = prevPanel ? prevPanel.scrollTop : null;
    const popoverTop = prevPopover ? prevPopover.scrollTop : null;
    root.innerHTML = `<div class="${cls.join(" ")}">${sidebarView()}${mainView()}${panelView()}</div>`;
    bind();
    const q = $("#q");
    if (q && keep) { q.value = keep.value; autosize(q); if (keep.focus) q.focus(); }
    const feed = $(".feed");
    const shouldScrollEnd = scrollFeed || state.scrollToEnd === true;
    state.scrollToEnd = false;
    if (feed) {
      if (shouldScrollEnd) {
        if (feedTop !== null) feed.scrollTop = feedTop;
        feed.scrollTo({ top: feed.scrollHeight, behavior: "smooth" });
      } else if (feedTop !== null) {
        feed.scrollTop = feedTop;
      }
    }
    const history = $(".history");
    if (history && historyTop !== null) history.scrollTop = historyTop;
    const panel = $(".panel-body");
    if (panel && panelTop !== null && !state.resetPanelScroll) panel.scrollTop = panelTop;
    state.resetPanelScroll = false;
    const popover = $(".popover-list");
    if (popover && popoverTop !== null) popover.scrollTop = popoverTop;
  }

  function sidebarView() {
    const limit = CFG.historyLimit;
    const list = state.showAllChats ? state.chats : state.chats.slice(0, limit);
    const groups = {};
    for (const c of list) (groups[dateGroup(c.updated)] ||= []).push(c);
    const order = ["history.today", "history.yesterday", "history.week", "history.older"];
    return `<nav class="sidebar" aria-label="${esc(t("history.label"))}">
      <div class="sidebar-head">
        <span class="brand" aria-label="RadLab — ${esc(DATA.brand)}">
          <img class="brand-logo brand-logo-light" src="/static/img/logo.png" width="300" height="88" alt="${esc(DATA.brand)}" fetchpriority="high">
          <img class="brand-logo brand-logo-dark" src="/static/img/logo-inverted.png" width="300" height="88" alt="${esc(DATA.brand)}">
        </span>
      </div>
      <button class="btn btn-new" data-act="new">${icon("plus")} ${esc(t("chat.new"))}</button>
      <div class="history">
        ${state.chats.length === 0 ? `<p class="section-empty">${esc(t("history.empty"))}</p>` : ""}
        ${order.filter((g) => groups[g]).map((g) => `<div class="history-label">${esc(t(g))}</div>${groups[g].map((c) =>
          `<button class="history-item" data-chat="${c.chat_id}" ${state.chatId === c.chat_id ? 'aria-current="true"' : ""} title="${esc(c.title)}">${esc(c.title)}</button>`).join("")}`).join("")}
        ${state.chats.length > limit && !state.showAllChats ? `<button class="btn btn-sm btn-ghost add-section" data-act="more-chats">${esc(t("history.more"))}</button>` : ""}
      </div>
      <div class="sidebar-foot">
        <span style="display:flex;align-items:center;gap:8px;min-width:0"><span class="avatar">${esc(initials(DATA.user))}</span><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(DATA.user)}</span></span>
        <span style="display:flex">
          ${CFG.languages.length > 1 ? `<a class="icon-btn" style="font-size:12px;font-weight:700;text-decoration:none" href="/lang/${CFG.lang === "pl" ? "en" : "pl"}?next=/" aria-label="${esc(t("ui.language"))}">${CFG.lang === "pl" ? "EN" : "PL"}</a>` : ""}
          <button class="icon-btn theme-toggle" data-act="theme" aria-label="${esc(t("ui.theme"))}">${icon("sun", "icon icon-sun")}${icon("moon", "icon icon-moon")}</button>
          <button class="icon-btn" data-act="logout" aria-label="${esc(t("ui.logout"))}">${icon("out")}</button>
        </span>
      </div>
      <div class="sidebar-rail">
        <img class="brand-mark" src="/static/img/small-ico.png" width="24" height="24" alt="${esc(DATA.brand)}">
        <button class="icon-btn" data-act="new" aria-label="${esc(t("chat.new"))}">${icon("plus")}</button>
        <button class="icon-btn" data-act="back" aria-label="${esc(t("history.show"))}">${icon("panel")}</button>
      </div>
    </nav>`;
  }

  function scopeChip() {
    if (!base()) return `<span class="scope-chip" aria-disabled="true">📚 <b>${esc(t("scope.unknown"))}</b></span>`;
    const n = sel().size, total = docs().length;
    const part = !total ? `${base().active_document_count ?? ""} ${docsWord(base().active_document_count || 0)}`
      : n === total ? t("scope.all", { n: total, word: docsWord(total) }) : t("scope.some", { n, total, word: t("word.document.many") });
    return `<span class="popover-anchor">
      <button class="scope-chip ${total && n !== total ? "is-partial" : ""}" data-act="popover-base" aria-haspopup="dialog" aria-expanded="${state.popover === "base"}">
        📚 <b>${esc(base().display_name)}</b><span class="part">· ${esc(part)}</span>${icon("down")}</button>
      ${state.popover === "base" ? basePopover() : ""}
    </span>`;
  }

  function mainView() {
    if (state.loading) return `<main class="main"><div class="topbar"></div><div class="welcome-wrap"><div class="welcome"><span class="spinner" role="status" aria-label="${esc(t("ui.loading"))}"></span></div></div></main>`;
    if (state.noAccess) return `<main class="main"><div class="topbar"></div><div class="welcome-wrap"><div class="welcome">
      <div class="notice notice-error" style="max-width:440px;text-align:left">${icon("warn")}<div><b>${esc(t("error.no_access.title"))}</b><br>${esc(t("error.no_access.text"))}</div></div></div></div></main>`;
    const empty = state.messages.length === 0;
    const busy = !!state.waiting;
    const none = base() && docs().length > 0 && sel().size === 0;
    const title = (state.chats.find((c) => c.chat_id === state.chatId) || {}).title || (state.messages.find((m) => m.role === "user") || {}).text || "";
    return `<main class="main">
      <header class="topbar">
        <span class="topbar-title">${empty ? "" : esc(title)}</span>
        <span class="topbar-actions">
          ${empty ? "" : `<button class="btn btn-sm" data-act="copy-all">${icon("copy")} ${esc(t("chat.copy_with_sources"))}</button>`}
          ${state.panel ? "" : `<button class="btn btn-sm btn-ghost" data-act="open-docs">${icon("docs")} ${esc(t("docs.title"))}</button>`}
        </span>
      </header>
      ${state.offline ? `<div class="notice notice-warn" role="status" style="margin:12px 24px 0">${icon("warn")}<div><b>${esc(t("error.unavailable.title"))}</b> ${esc(t("error.unavailable.text"))} <button class="page-link" data-act="recheck">${esc(t("ui.refresh"))}</button></div></div>` : ""}
      ${empty ? `<div class="welcome-wrap"><div class="welcome">
          <h1 class="display display-xl">${esc(t("chat.welcome.title"))}</h1>
          <p>${esc(t("chat.welcome.text"))}</p></div></div>`
        : `<div class="feed" aria-live="polite"><div class="feed-inner">${state.messages.map(messageView).join("")}</div></div>`}
      <div class="composer">
        <div class="composer-box ${busy ? "is-disabled" : ""}">
          <label class="sr-only" for="q">${esc(t("chat.question"))}</label>
          <textarea id="q" rows="1" maxlength="8000" placeholder="${esc(busy ? t("chat.placeholder.wait") : empty ? t("chat.placeholder.first") : t("chat.placeholder.follow"))}" ${busy ? "disabled" : ""}></textarea>
          <div class="composer-row"><span class="composer-chips">${scopeChip()}
            <span class="popover-anchor">
              <button class="scope-chip" data-act="popover-format" aria-haspopup="dialog" aria-expanded="${state.popover === "format"}">${icon("list")}<b>${esc(fmtById(state.format).label)}</b>${icon("down")}</button>
              ${state.popover === "format" ? formatPopover() : ""}
            </span></span>
            <button class="send" data-act="send" aria-label="${esc(t("chat.send"))}" ${busy || none ? "disabled" : ""}>${icon("send")}</button></div>
        </div>
        <p class="composer-hint">${none ? `<b>${esc(t("scope.none"))}</b>` : esc(t("chat.disclaimer"))}</p>
      </div>
    </main>`;
  }

  function basePopover() {
    return `<div class="popover popover--base" role="dialog" aria-label="${esc(t("base.choose"))}">
      <p class="eyebrow" style="margin:4px 8px 8px">${esc(t("base.label"))}</p>
      <div class="popover-list">
        ${state.collections.map((c) => `<button class="base-card" role="menuitemradio" aria-checked="${c.name === state.baseName}" data-base="${esc(c.name)}">
          <b>${esc(c.display_name)}</b>${c.description ? `<span>${esc(c.description)}</span>` : ""}<span>${c.active_document_count ?? "–"} ${docsWord(c.active_document_count || 0)}</span></button>`).join("")}
      </div>
    </div>`;
  }

  function formatPopover() {
    return `<div class="popover popover--format" role="dialog" aria-label="${esc(t("format.label"))}">
      <p class="eyebrow" style="margin:4px 8px 8px">${esc(t("format.question"))}</p>
      <div class="popover-list">
        ${CFG.formats.map((f) => `<button class="base-card" role="menuitemradio" aria-checked="${f.id === state.format}" data-format="${esc(f.id)}"><b>${esc(f.label)}</b><span>${esc(f.description)}</span></button>`).join("")}
      </div>
      <p class="small muted" style="margin:8px 8px 2px">${esc(t("format.remember"))}</p></div>`;
  }

  /* ---------- Messages ---------- */
  function messageView(m, i) {
    if (m.role === "user") return `<div class="msg-user">${esc(m.text)}${m.format ? `<span class="fmt-tag">${esc(fmtById(m.format).label)}</span>` : ""}</div>`;
    if (m.role === "scope") return `<div class="scope-line">${esc(m.text)}</div>`;
    if (m.role === "notice") return `<div class="notice">${icon("info")}<div>${esc(m.text)}</div></div>`;
    if (m.role === "thinking") return `<div class="thinking" role="status">
        <div class="thinking-row"><span class="spinner" aria-hidden="true"></span><b>${esc(m.label)}</b><span class="timer">${m.seconds} s</span></div>
        ${m.seconds >= 30 ? `<div class="small muted">${esc(t("wait.long"))}</div>` : ""}
        <div><button class="btn btn-sm" data-act="stop">${esc(t("wait.stop"))}</button></div></div>`;
    if (m.role === "error") return `<div class="notice notice-error" role="alert">${icon("warn")}<div><b>${esc(t(`error.${m.kind}.title`))}</b><br>${esc(m.message || t(`error.${m.kind}.text`))}
        <div class="actions"><button class="btn btn-sm" data-act="retry" data-i="${i}">${icon("retry")} ${esc(t("ui.retry"))}</button><button class="btn btn-sm btn-ghost" data-act="edit" data-i="${i}">${esc(t("chat.edit_question"))}</button></div></div></div>`;
    if (m.legacy) return `<div class="msg-assistant"><div class="answer">${m.html}</div>
        <div class="notice">${icon("info")}<div>${esc(t("history.no_sources"))}
        <div class="actions"><button class="btn btn-sm" data-act="retry" data-i="${i}">${icon("retry")} ${esc(t("history.ask_again"))}</button></div></div></div></div>`;
    const a = m.answer;
    if (a.no_sources) return `<div class="msg-assistant">
        <div class="notice notice-warn">${icon("warn")}<div><b>${esc(a.scope_count != null ? t("answer.no_sources.selected") : t("answer.no_sources.base", { base: m.baseLabel || "" }))}</b> ${esc(t("answer.no_sources.text"))}
          <div class="actions"><button class="btn btn-sm" data-act="edit" data-i="${i}">${esc(t("chat.edit_question"))}</button>
          ${a.scope_count != null ? `<button class="btn btn-sm" data-act="select-all">${esc(t("answer.search_all"))}</button>` : `<button class="btn btn-sm" data-act="popover-base">${esc(t("answer.other_base"))}</button>`}</div></div></div>
        <div class="answer is-muted">${a.html}</div>${actionsView(m, i, false)}</div>`;
    const scopeCount = a.scope_count ?? m.baseCount;
    return `<div class="msg-assistant" data-i="${i}">
      <div class="answer">${a.html}</div>
      <div class="coverage">${esc(t(a.scope_count != null ? "answer.coverage.selected" : "answer.coverage", { used: a.documents_used, total: scopeCount ?? "?", fragments: a.fragments }))}</div>
      <div class="sources">${a.groups.map((g, gi) => sourceView(g, i, gi, m)).join("")}</div>
      ${a.cited ? `<div class="approx-note"><span class="fn approx" aria-hidden="true">1</span>${esc(t("answer.approx_note"))}</div>` : `<div class="approx-note">${esc(t("answer.no_citations"))}</div>`}
      ${actionsView(m, i, true)}</div>`;
  }

  function sourceView(g, mi, gi, m) {
    const open = m.open === gi;
    return `<div class="source" open-state="${open}">
      <button class="source-head" data-act="toggle-src" data-i="${mi}" data-g="${gi}" aria-expanded="${open}">
        <span class="n">[${g.n}]</span>${g.filetype ? `<span class="filetype">${esc(g.filetype)}</span>` : ""}<span class="name">${esc(g.stem)}</span>
        <span class="pages">${g.pages.length ? esc(t("answer.pages", { pages: g.pages.join(", ") })) : ""}</span>${icon("chev", "icon chev")}</button>
      ${open ? `<div class="source-body">${g.fragments.map((f, fi) => `<div><div class="quote">${f.left ? "…" + esc(f.left) + " " : ""}<b>${esc(f.text)}</b>${f.right ? " " + esc(f.right) + "…" : ""}</div>
        <button class="page-link" data-act="open-fragment" data-i="${mi}" data-g="${gi}" data-f="${fi}">${esc(f.page ? t("answer.open_page", { page: f.page }) : t("answer.open_doc"))} →</button></div>`).join("")}</div>` : ""}
    </div>`;
  }

  function actionsView(m, i, reformat) {
    const a = m.answer;
    const canRate = a.answer_id != null;
    return `<div class="msg-actions">
      <button class="icon-btn" data-act="copy" data-i="${i}" aria-label="${esc(t("answer.copy"))}">${icon("copy")}</button>
      ${canRate ? `<button class="icon-btn" data-act="rate-up" data-i="${i}" aria-label="${esc(t("answer.useful"))}" aria-pressed="${m.rating === 1}">${icon("up")}</button>
      <button class="icon-btn" data-act="rate-down" data-i="${i}" aria-label="${esc(t("answer.not_useful"))}" aria-pressed="${m.rating === 0}">${icon("dn")}</button>` : ""}
      <span class="meta">${esc(fmtById(a.format).label)}${a.generation_time != null ? " · " + esc(t("answer.time", { time: seconds(a.generation_time) })) : ""}</span></div>
      ${m.feedback ? `<form class="feedback" data-i="${i}"><label class="sr-only" for="fb${i}">${esc(t("answer.feedback.label"))}</label><input class="input input-sm" id="fb${i}" maxlength="2000" placeholder="${esc(t("answer.feedback.placeholder"))}"><button class="btn btn-sm" type="submit">${esc(t("ui.send"))}</button></form>` : ""}
      ${reformat && a.question ? `<div class="reformat"><span>${esc(t("format.other"))}</span>${CFG.formats.filter((f) => f.id !== a.format).map((f) =>
        `<button class="chip-link" data-act="reformat" data-i="${i}" data-f="${esc(f.id)}">${esc(f.label)}</button>`).join("")}</div>` : ""}`;
  }

  /* ---------- Panel: documents and preview ---------- */
  function panelView() {
    if (!state.panel || state.noAccess || state.loading) return `<aside class="panel" aria-hidden="true"></aside>`;
    if (state.panel === "doc") return docView();
    const head = `<div class="panel-head"><h2>${esc(t("docs.title"))}</h2><button class="icon-btn" data-act="close-panel" aria-label="${esc(t("docs.collapse"))}">${icon("x")}</button></div>`;
    if (!base()) return `<aside class="panel" aria-label="${esc(t("docs.title"))}">${head}<div class="panel-body"><p class="small muted">${esc(t("docs.unknown_base"))}</p></div></aside>`;
    const all = docs();
    if (!state.docs[state.baseName]) return `<aside class="panel">${head}<div class="panel-body"><span class="spinner" role="status" aria-label="${esc(t("ui.loading"))}"></span></div></aside>`;
    const q = state.docFilter.toLowerCase();
    const list = all.filter((d) => d.name.toLowerCase().includes(q));
    const n = sel().size, total = all.length;
    return `<aside class="panel" aria-label="${esc(t("docs.title"))}">${head}
      <div class="panel-body">
        <div class="panel-sub"><b style="color:var(--text)">${esc(base().display_name)}</b>${base().description ? " · " + esc(base().description) : ""}</div>
        ${total > 10 ? `<div style="position:relative;margin-bottom:8px"><svg class="icon" aria-hidden="true" style="position:absolute;left:12px;top:9px;color:var(--text-muted)"><use href="#i-search"/></svg><input class="input input-sm" id="docfilter" placeholder="${esc(t("docs.search"))}" value="${esc(state.docFilter)}" aria-label="${esc(t("docs.search"))}" style="width:100%;padding-left:36px"></div>` : ""}
        ${total ? `<label class="doc-select-all"><span>${esc(t("docs.select_all"))} <span class="muted" style="font-weight:400">(${n} / ${total})</span></span>
          <input type="checkbox" class="check" id="selall" ${n === total ? "checked" : ""}></label>` : `<p class="small muted">${esc(t("docs.empty"))}</p>`}
        ${list.map((d) => `<div class="doc-row">
          <button class="doc-open" data-act="open-doc" data-doc="${esc(d.name)}" title="${esc(d.name)}">${d.filetype ? `<span class="filetype">${esc(d.filetype)}</span>` : ""}<span>${esc(d.stem)}</span></button>
          <input type="checkbox" class="check" data-doc-check="${esc(d.name)}" aria-label="${esc(t("docs.include", { name: d.stem }))}" ${sel().has(d.name) ? "checked" : ""}></div>`).join("")}
        ${total && !list.length ? `<p class="small muted" style="padding:8px">${esc(t("docs.no_match"))}</p>` : ""}
      </div>
      <div class="panel-foot">${esc(t("docs.footer"))}</div></aside>`;
  }

  function docView() {
    const d = state.doc;
    const head = `<div class="panel-head"><button class="btn btn-sm btn-ghost" data-act="back">${icon("back")} ${esc(t("docs.title"))}</button>
      <button class="icon-btn" data-act="close-panel" aria-label="${esc(t("doc.close"))}">${icon("x")}</button></div>`;
    if (d.loading) return `<aside class="panel">${head}<div class="panel-body"><span class="spinner" role="status" aria-label="${esc(t("ui.loading"))}"></span></div></aside>`;
    if (d.error) return `<aside class="panel">${head}<div class="panel-body"><div class="notice notice-error">${icon("warn")}<div><b>${esc(t(d.error === "not_found" || d.error === "backend" ? "error.document.title" : `error.${d.error}.title`))}</b><br>${esc(d.message || t("error.document.text"))}</div></div></div></aside>`;
    let quoteShown = false;
    const pages = d.pages.map((p) => {
      let body = esc(p.content);
      if (d.highlight && !quoteShown && p.page === d.from) {
        const hit = findQuote(p.content, d.highlight);
        if (hit) { body = esc(p.content.slice(0, hit[0])) + `<mark class="hl" id="hl">${esc(p.content.slice(hit[0], hit[1]))}</mark>` + esc(p.content.slice(hit[1])); quoteShown = true; }
      }
      return `<article class="doc-page"><h4>${esc(t("doc.page", { page: p.page }))}</h4><div style="white-space:pre-wrap">${body}</div></article>`;
    }).join("");
    const quoteBox = d.highlight && !quoteShown ? `<div class="notice" style="margin-bottom:12px">${icon("info")}<div><b>${esc(t("doc.quote"))}</b><br><mark class="hl" id="hl">${esc(d.highlight)}</mark></div></div>` : "";
    return `<aside class="panel" aria-label="${esc(t("doc.preview"))}">${head}
      <div class="panel-body">
        <h2 class="display" style="font-size:21px;margin:0 4px 8px">${esc(stemOf(d.name))}</h2>
        <div class="doc-meta">${typeOf(d.name) ? `<span class="filetype">${esc(typeOf(d.name))}</span>` : ""}${esc(t("doc.page_of", { page: d.from, total: d.total ?? "?" }))}${d.approx ? " · " + esc(t("doc.approx")) : ""}</div>
        ${quoteBox}${pages || `<p class="small muted">${esc(t("doc.empty"))}</p>`}
        ${d.next ? `<div style="text-align:center"><button class="btn btn-sm" data-act="more-pages">${esc(t("doc.more"))}</button></div>` : ""}
      </div>
      <div class="panel-foot">${esc(t("doc.extracted"))}</div></aside>`;
  }

  /* ---------- Actions ---------- */
  async function loadDocs(name) {
    if (!name || state.docs[name]) return;
    const r = await api(`/ui-api/documents?collection=${encodeURIComponent(name)}`);
    state.docs[name] = r.ok ? r.data.documents : [];
    if (!state.selected[name]) state.selected[name] = new Set(state.docs[name].map((d) => d.name));
    render();
  }

  async function loadChats() {
    const r = await api("/ui-api/chats");
    if (r.ok) { state.chats = r.data.chats; render(); }
  }

  async function send(question, format = state.format) {
    question = question.trim();
    if (!question || state.waiting || !base() && state.chatId === null) return;
    if (base() && docs().length && sel().size === 0) return;
    state.popover = false;
    const documents = base() && docs().length && !allSelected() ? [...sel()] : null;
    const label = base()
      ? t("wait.searching", { n: documents ? documents.length : (docs().length || base().active_document_count || ""), word: t("word.document.loc"), base: base().display_name })
      : t("wait.searching_chat");
    state.messages.push({ role: "user", text: question, format });
    const thinking = { role: "thinking", seconds: 0, label };
    state.messages.push(thinking);
    const controller = new AbortController();
    const started = Date.now();
    const timer = setInterval(() => {
      thinking.seconds = Math.floor((Date.now() - started) / 1000);
      const el = $(".thinking .timer");
      if (el) el.textContent = `${thinking.seconds} s`;
      if (thinking.seconds === 30) { state.scrollToEnd = false; render(); }
    }, 500);
    const hardTimeout = setTimeout(() => controller.abort("timeout"), (CFG.answerTimeoutS + 5) * 1000);
    state.waiting = { controller, timer, thinking };
    if ($("#q")) $("#q").value = "";
    render(true);

    const r = await api("/ui-api/ask", {
      method: "POST", signal: controller.signal,
      body: { question, collection: state.baseName, chat_id: state.chatId, documents, format },
    });
    clearInterval(timer); clearTimeout(hardTimeout);
    state.waiting = null;
    state.messages = state.messages.filter((m) => m !== thinking);
    if (r.ok) {
      const isNew = state.chatId === null;
      state.chatId = r.data.chat_id;
      state.messages.push({ role: "assistant", answer: r.data.answer, baseLabel: base() ? base().display_name : "", baseCount: docs().length || (base() && base().active_document_count) });
      if (isNew) loadChats();
    } else if (r.error === "aborted" && controller.signal.reason !== "timeout") {
      toast(t("wait.stopped"));
    } else {
      const kind = r.error === "aborted" ? "timeout" : ["timeout", "unavailable", "forbidden", "no_documents"].includes(r.error) ? r.error : "backend";
      if (kind === "unavailable") state.offline = true;
      state.messages.push({ role: "error", kind, message: kind === "backend" ? r.message : "", question, format });
    }
    render(true);
  }

  function stop() {
    if (state.waiting) state.waiting.controller.abort("user");
  }

  function newChat(baseName) {
    if (state.waiting) stop();
    if (baseName) { state.baseName = baseName; store.set("rag-base", baseName); state.resetPanelScroll = true; loadDocs(baseName); }
    else if (!base() && state.collections.length) state.baseName = state.collections[0].name;
    state.chatId = null; state.messages = []; state.popover = false;
    if (state.panel === "doc") state.panel = "docs";
    render(); $("#q")?.focus();
  }

  async function openChat(id) {
    if (state.waiting) stop();
    const r = await api(`/ui-api/chats/${id}`);
    if (!r.ok) { toast(t("error.backend.title")); return; }
    const d = r.data;
    state.chatId = id; state.popover = false;
    if (state.panel === "doc") state.panel = "docs";
    const known = d.collection && state.collections.some((c) => c.name === d.collection);
    state.baseName = known ? d.collection : null;
    state.messages = d.messages.map((m) => m.role === "user" ? { role: "user", text: m.text }
      : m.legacy ? { role: "assistant", legacy: true, html: m.html, plain: m.plain, question: m.question }
      : { role: "assistant", answer: m.answer, baseLabel: known ? base().display_name : "" });
    if (known) {
      await loadDocs(d.collection);
      state.selected[d.collection] = new Set(d.documents || docs().map((x) => x.name));
    } else {
      state.messages.push({ role: "notice", text: t("history.unknown_base") });
    }
    state.resetPanelScroll = true;
    render(true);
  }

  async function openDoc(name, page = 1, highlight = null, approx = false) {
    if (!base()) return;
    state.panel = "doc";
    state.doc = { name, from: page, pages: [], highlight, approx, loading: true };
    state.resetPanelScroll = true;
    render();
    const r = await api(`/ui-api/document?collection=${encodeURIComponent(state.baseName)}&name=${encodeURIComponent(name)}&from_page=${page}`);
    if (!state.doc || state.doc.name !== name) return;
    if (!r.ok) { state.doc = { name, error: r.error, message: r.error === "backend" ? r.message : "" }; render(); return; }
    Object.assign(state.doc, { loading: false, pages: r.data.pages, total: r.data.total_pages, next: r.data.next_page });
    state.resetPanelScroll = true;
    render();
    $("#hl")?.scrollIntoView({ block: "center" });
  }

  async function morePages() {
    const d = state.doc;
    const r = await api(`/ui-api/document?collection=${encodeURIComponent(state.baseName)}&name=${encodeURIComponent(d.name)}&from_page=${d.next}`);
    if (r.ok) { d.pages.push(...r.data.pages); d.next = r.data.next_page; state.scrollToEnd = false; render(); }
  }

  function scopeChanged() {
    if (!state.messages.length) return;
    const n = sel().size, total = docs().length;
    const text = n === total ? t("scope.line.all", { n: total, word: docsWord(total) }) : t("scope.line.some", { n, total, word: t("word.document.many") });
    const last = state.messages[state.messages.length - 1];
    if (last.role === "scope") last.text = text; else state.messages.push({ role: "scope", text });
  }

  async function rate(i, value, comment) {
    const m = state.messages[i];
    const r = await api("/ui-api/rate", { method: "POST", body: { answer_id: m.answer.answer_id, value, comment } });
    if (r.ok) toast(comment ? t("answer.feedback.sent") : t("answer.rated"));
    else toast(t("error.backend.title"));
  }

  function plainOf(m) {
    if (m.legacy) return m.plain;
    return m.answer.plain;
  }

  function copyAll() {
    const lines = [];
    for (const m of state.messages) {
      if (m.role === "user") lines.push(`${t("copy.question")}: ${m.text}`);
      if (m.role === "assistant") {
        lines.push(`${t("copy.answer")}: ${plainOf(m)}`);
        if (m.answer && m.answer.groups.length) lines.push(`${t("copy.sources")}:\n` + m.answer.groups.map((g) => `[${g.n}] ${g.stem}${g.pages.length ? ", " + t("answer.pages", { pages: g.pages.join(", ") }) : ""}`).join("\n"));
      }
    }
    if (base()) lines.push(`${t("base.label")}: ${base().display_name}`);
    copyText(lines.join("\n\n"), t("chat.copied_with_sources"));
  }

  function copyText(text, message) {
    const done = () => toast(message);
    if (navigator.clipboard && window.isSecureContext) navigator.clipboard.writeText(text).then(done, () => fallbackCopy(text, done));
    else fallbackCopy(text, done);
  }

  function fallbackCopy(text, done) {
    const ta = document.createElement("textarea");
    ta.value = text; ta.style.position = "fixed"; ta.style.opacity = "0";
    document.body.appendChild(ta); ta.select();
    try { document.execCommand("copy"); done(); } catch { toast(t("error.copy")); }
    ta.remove();
  }

  let toastTimer;
  function toast(text) {
    const o = $("#overlay");
    o.querySelector(".toast")?.remove();
    o.insertAdjacentHTML("beforeend", `<div class="toast" role="status">${esc(text)}</div>`);
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => o.querySelector(".toast")?.remove(), 3500);
  }

  function confirmDialog(title, text, ok, onOk, cancel = true) {
    const o = $("#overlay");
    o.querySelector(".dialog-backdrop")?.remove();
    o.insertAdjacentHTML("beforeend", `<div class="dialog-backdrop"><div class="dialog" role="alertdialog" aria-modal="true" aria-labelledby="dlg-t">
      <h3 id="dlg-t">${esc(title)}</h3><p>${esc(text)}</p>
      <div class="actions">${cancel ? `<button class="btn" data-d="cancel">${esc(t("ui.cancel"))}</button>` : ""}<button class="btn btn-primary" data-d="ok">${esc(ok)}</button></div></div></div>`);
    const bd = o.querySelector(".dialog-backdrop");
    bd.querySelector('[data-d="ok"]').focus();
    bd.addEventListener("click", (e) => {
      const d = e.target.closest("[data-d]")?.dataset.d;
      if (d || (e.target === bd && cancel)) { bd.remove(); if (d === "ok") onOk(); }
    });
  }

  let expiredShown = false;
  function sessionExpired() {
    if (expiredShown) return;
    expiredShown = true;
    confirmDialog(t("error.session.title"), t("error.session.text"), t("login.submit"), () => { location.href = "/login"; }, false);
  }

  /* ---------- Events ---------- */
  function bind() {
    const q = $("#q");
    if (q) {
      q.addEventListener("input", () => autosize(q));
      q.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(q.value); } });
    }
    $("#docfilter")?.addEventListener("input", (e) => {
      state.docFilter = e.target.value; const pos = e.target.selectionStart; render();
      const f = $("#docfilter"); f.focus(); f.setSelectionRange(pos, pos);
    });
    const all = $("#selall");
    if (all) {
      all.indeterminate = sel().size > 0 && !allSelected();
      all.addEventListener("change", () => {
        state.selected[state.baseName] = all.checked ? new Set(docs().map((d) => d.name)) : new Set();
        scopeChanged(); render();
      });
    }
    document.querySelectorAll("[data-doc-check]").forEach((c) => c.addEventListener("change", () => {
      const s = sel(); c.checked ? s.add(c.dataset.docCheck) : s.delete(c.dataset.docCheck);
      scopeChanged(); render();
    }));
    document.querySelectorAll("form.feedback").forEach((f) => f.addEventListener("submit", (e) => {
      e.preventDefault();
      const i = +f.dataset.i;
      const comment = f.querySelector("input").value;
      state.messages[i].feedback = false; render();
      rate(i, 0, comment);
    }));
  }

  function autosize(q) { q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 200) + "px"; }

  document.addEventListener("click", (e) => {
    const el = e.target.closest("[data-act],[data-base],[data-chat],[data-format],.fn[data-fn]");
    if (state.popover && !e.target.closest(".popover,[data-act^='popover']")) { state.popover = false; if (!el) { render(); return; } }
    if (!el) return;
    if (el.matches(".fn[data-fn]")) {
      const mi = +el.closest(".msg-assistant").dataset.i, g = state.messages[mi].answer.groups.find((x) => x.n === +el.dataset.fn);
      document.querySelectorAll(".fn[aria-current]").forEach((f) => f.removeAttribute("aria-current"));
      openDoc(g.name, g.page || 1, g.quote, true);
      return;
    }
    if (el.dataset.base) {
      const b = el.dataset.base; state.popover = false;
      if (b === state.baseName) { render(); return; }
      if (state.messages.length) {
        const c = state.collections.find((x) => x.name === b);
        confirmDialog(t("base.switch.title", { base: c.display_name }), t("base.switch.text"), t("base.switch.ok"), () => newChat(b));
        render();
      } else newChat(b);
      return;
    }
    if (el.dataset.format) { state.format = el.dataset.format; store.set("rag-format", state.format); state.popover = false; render(); $("#q")?.focus(); return; }
    if (el.dataset.chat) { openChat(+el.dataset.chat); return; }
    const a = el.dataset.act, i = el.dataset.i !== undefined ? +el.dataset.i : null, m = i !== null ? state.messages[i] : null;
    switch (a) {
      case "send": send($("#q").value); break;
      case "stop": stop(); break;
      case "new": newChat(); break;
      case "popover-base": state.popover = state.popover === "base" ? false : "base"; if (!state.panel) state.panel = "docs"; render(); break;
      case "popover-format": state.popover = state.popover === "format" ? false : "format"; render(); break;
      case "open-docs": state.panel = "docs"; store.set("rag-panel", "open"); render(); break;
      case "close-panel": state.panel = null; store.set("rag-panel", "closed"); render(); break;
      case "back": state.panel = "docs"; render(); break;
      case "open-doc": openDoc(el.dataset.doc, 1); break;
      case "open-fragment": { const g = m.answer.groups[+el.dataset.g], f = g.fragments[+el.dataset.f]; openDoc(g.name, f.page || 1, f.text, false); break; }
      case "more-pages": morePages(); break;
      case "toggle-src": m.open = m.open === +el.dataset.g ? null : +el.dataset.g; state.scrollToEnd = false; render(); break;
      case "copy": copyText(plainOf(m), t("answer.copied")); break;
      case "copy-all": copyAll(); break;
      case "rate-up": m.rating = 1; m.feedback = false; state.scrollToEnd = false; render(); rate(i, 1, null); break;
      case "rate-down": m.rating = 0; m.feedback = true; state.scrollToEnd = false; render(); $(`#fb${i}`)?.focus(); break;
      case "reformat": send(m.answer.question, el.dataset.f); break;
      case "retry": {
        const q = m.question || m.answer?.question; const f = m.format;
        state.messages = state.messages.filter((x) => x.role !== "error");
        send(q, f || state.format); break;
      }
      case "edit": {
        const q = m.question || m.answer?.question || "";
        state.messages = state.messages.filter((x) => x.role !== "error"); render();
        const ta = $("#q"); ta.value = q; autosize(ta); ta.focus(); break;
      }
      case "select-all": state.selected[state.baseName] = new Set(docs().map((d) => d.name)); scopeChanged(); render(); break;
      case "more-chats": state.showAllChats = true; render(); break;
      case "theme": {
        const r = document.documentElement;
        const dark = r.dataset.theme ? r.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
        r.dataset.theme = dark ? "light" : "dark";
        store.set("rag-theme", r.dataset.theme);
        store.set("radlab-theme", r.dataset.theme);
        break;
      }
      case "logout": $("#logout-form").submit(); break;
      case "recheck": checkHealth(true); break;
    }
  });

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const dlg = $(".dialog-backdrop");
    if (dlg && dlg.querySelector('[data-d="cancel"]')) { dlg.remove(); return; }
    if (state.popover) { state.popover = false; render(); return; }
    if (state.panel === "doc") { state.panel = "docs"; render(); }
  });

  /* ---------- Helpers ---------- */
  function stemOf(name) { return name.replace(/\.[A-Za-z0-9]{1,5}$/, ""); }
  function typeOf(name) { const m = name.match(/\.([A-Za-z0-9]{1,5})$/); return m ? m[1].toUpperCase() : ""; }
  function initials(name) { return (name || "?").split(/[\s._@-]+/).filter(Boolean).slice(0, 2).map((p) => p[0].toUpperCase()).join("") || "?"; }

  function dateGroup(iso) {
    if (!iso) return "history.older";
    const d = new Date(iso), now = new Date();
    const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = Math.round((day(now) - day(d)) / 86400000);
    if (diff <= 0) return "history.today";
    if (diff === 1) return "history.yesterday";
    if (diff < 7) return "history.week";
    return "history.older";
  }

  /* Quote in the page text: matching resilient to spacing and line-break differences (until CR-02). */
  function findQuote(content, quote) {
    const norm = (s) => s.toLowerCase().replace(/\s+/g, " ");
    const hay = norm(content), needle = norm(quote).trim();
    if (!needle) return null;
    for (const len of [needle.length, 160, 80]) {
      const part = needle.slice(0, Math.min(len, needle.length));
      const at = hay.indexOf(part);
      if (at >= 0) return mapRange(content, at, at + (len === needle.length ? needle.length : part.length));
    }
    return null;
  }

  function mapRange(content, start, end) {
    // Positions in the normalized text -> positions in the original.
    let ni = 0, s = -1, inSpace = false;
    for (let i = 0; i < content.length; i++) {
      const space = /\s/.test(content[i]);
      if (space && inSpace) continue;
      inSpace = space;
      if (ni === start && s < 0) s = i;
      ni++;
      if (ni === end) return [s < 0 ? i : s, i + 1];
    }
    return s >= 0 ? [s, content.length] : null;
  }

  async function checkHealth(manual) {
    const r = await fetch("/ui-api/health", { credentials: "same-origin" }).then((x) => x.ok, () => false);
    state.offline = !r;
    if (manual || !r) render();
  }

  /* ---------- Start ---------- */
  async function init() {
    render();
    const [cols] = await Promise.all([api("/ui-api/collections"), checkHealth(false)]);
    state.loading = false;
    if (!cols.ok) {
      if (cols.error === "forbidden") state.noAccess = true;
      else if (cols.error === "unavailable" || cols.error === "timeout") state.offline = true;
      render(); return;
    }
    state.collections = cols.data.collections;
    if (!state.collections.length) { state.noAccess = true; render(); return; }
    const last = store.get("rag-base", "");
    state.baseName = state.collections.some((c) => c.name === last) ? last : state.collections[0].name;
    render();
    loadDocs(state.baseName);
    loadChats();
  }

  init();
})();
