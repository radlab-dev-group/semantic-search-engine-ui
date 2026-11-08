# 03 – Change requests for the RadLab backend

Version 0.4 · 2026-11-01 (API gaps list, CR-19, CR-05 supplement) · addressee: the `semantic-search-engine` team (RadLab)
Based on: backend code analysis (commit 58c0b8d, 2026-10-30), the user journey `04-sciezka-uzytkownika.html`
and the benchmark `benchmark/2026-11-01-insp-board.html`.

## API gaps the interface needs

Endpoints and fields that do not exist today but that the interface already anticipates. "MVP" means the element is in the MVP
in a transitional form (with a visible limitation) or hidden behind a flag until the change lands.

| # | What is missing (endpoint / field) | UI element that needs it | Until the change | CR |
|---|---|---|---|---|
| 1 | Conversation history (questions **and answers**) passed to the model that generates the RAG answer; `rewritten_query` field | follow-up questions ("expand", "make a table"), "Show as:" without a new search | the model only sees the 4 previous questions appended to the search | CR-14 |
| 2 | Numbered fragments in the prompt and a `citations[]` field (`n`, `text_id`, `document_name`, `page_number`, `char_start`, `char_end`) in `add_user_message` | [n] footnotes next to sentences | approximate footnote: document certain, page chosen | CR-01 |
| 3 | `text_id`, `document_id`, `char_start`, `char_end` in `detailed_results_json`; `document_content?text_id=` | quote highlighting in the document preview | searching for the quote text in the page content on the frontend | CR-02 |
| 4 | `answer_source: "rag" \| "llm_fallback"` in `add_user_message`; the `rag_only` option | the "I didn't find this in the documents" warning | inferring it from an empty `detailed_results_json` | CR-03 |
| 5 | `GET chats?with_sources=true` – message state (sources, `sse_answer.id`) | sources, footnotes and rating for older answers | "sources unavailable" message + "Ask again" | CR-04 |
| 6 | In `GET chats`: `title`, **`collection_name`**, `created_at`, `updated_at`, `messages_count`, pagination (`limit`, `offset`) | history: title, date, conversation base, fast loading | title = first question; the base of a resumed conversation is only known in the current frontend session | CR-05 |
| 7 | `POST rename_chat`, `POST delete_chat` | the ⋯ menu next to a conversation: Rename, Delete | hidden (flag `features.chat_sections`) | CR-05 |
| 8 | `GET/POST chat_groups`, `rename_chat_group`, `delete_chat_group`, `POST move_chat`, `POST pin_chat`, `group_id` in `new_chat`, `group_id` and `pinned` in `chats` | sections in the history, pinning, "+" new chat in a section | hidden (flag `features.chat_sections`) | CR-16 |
| 9 | Document scope stored with the chat; `documents` in `GET chats` | the Documents panel after resuming a conversation | after resuming, the scope falls back to "all", with a message | CR-18 |
| 10 | `POST cancel_generation` (`chat_id`) | the "Stop" button | only stops waiting in the UI; the answer may still appear in history | CR-06 |
| 11 | Progress events / streaming (SSE) from `add_user_message` | stages "searching / found / writing", live text | a seconds counter | CR-06 |
| 12 | In `GET documents`: `document_date`, `uploaded_at`, `file_type`, `total_pages` | Documents panel: date, page count | only the name and the type taken from the extension | CR-07 |
| 13 | `system_prompt` from the request merged with the question-template prompt instead of overwritten | answer format (Brief / Bullet points / Detailed / Table), the citation instruction | in collections with templates the format and footnotes may not work | CR-19 |

Outside the MVP (roadmap): downloading the original file (CR-07), sharing inside the organisation (CR-08), agents (CR-09…12),
question refinement (CR-15), notes (CR-17), PPTX/XLSX/CSV (CR-13).

## Priorities
- **P0 – blocking.** Must-have requirement; without the change the frontend only works in transitional mode.
- **P1 – important for the MVP.** The frontend has a workaround, but with a visible limitation for the employee.
- **P2 – next version.**
- **R – agent roadmap.** The foundation for agents that query the base many times to prepare material.

## Summary

| ID | Priority | Topic | Blocks |
|---|---|---|---|
| CR-14 | **P0** | Conversation memory: the model knows earlier questions, answers and sources | follow-up questions in the chat |
| CR-01 | **P0** | Footnotes: sentence → fragment → page | the must-have footnotes |
| CR-02 | **P0** | Fragment identifiers and position in results | CR-01, preview highlighting, agents |
| CR-03 | P1 | Explicit marking of document-less answers and the ability to disable the fallback | trust |
| CR-04 | P1 | Sources and footnotes stored with chat messages (the employee view; complements CR-14) | history with sources |
| CR-05 | P1 | Chat management: title, deletion, pagination | history |
| CR-06 | P2 | Progress, streaming and stopping generation | long waits, the "Stop" button |
| CR-07 | P2 | Document metadata: date, version, type, page count; downloading the original | currency, verification, base preview |
| CR-08 | P2 | Sharing a chat within the organisation | sharing |
| CR-09 | R | Async jobs API for agents | agents |
| CR-10 | R | Batch search and fragment deduplication | agents |
| CR-11 | R | Agent work trace and citations in long material | agents |
| CR-12 | R | Plan steps and clarifying questions | agents |
| CR-18 | P1 | Document selection remembered with the chat | resuming a conversation with the same scope |
| CR-19 | P1 | `system_prompt` from the request not overwritten by question templates | answer format, footnotes |
| CR-15 | P2 | Refining the question before sending | bad and too-terse questions |
| CR-16 | **P1** | Sections in the history and pinning conversations (UI ready in the MVP behind a flag) | order in the history |
| CR-17 | R | Notes from answers for reuse | working with gathered material, agents |
| CR-13 | later | PPTX, XLSX, CSV support | tabular data |

---

## CR-14 · P0 · Conversation memory as context (decision 2026-11-01)

> Additional reason: the "Show as:" button (changing the answer format) currently reruns the whole search.
> With conversation memory the backend would reformat the previous answer without searching, in a few seconds.

**Requirement.** The backend remembers the whole conversation and uses it as context for every next answer.
The employee follows up like in a conversation with a person ("which of those apply to small firms?", "expand point 2",
"turn it into a table"), and the answer takes earlier questions, answers and sources into account.

**Current state (code, commit 58c0b8d).**
- The conversation is stored in the database: each message is a `Message` with a number and a previous/next message.
  Storage works; the problem is what reaches the model.
- **The model writing the RAG answer does not get the history.** `_prepare_rag_supervisor_state`
  (`chat/controllers/message.py`, around lines 160–230) calls `generative_answer_for_response`
  (`engine/controllers/models_logic/generative.py:516`) with only the search results and the query.
  The history with assistant answers (`_convert_to_history_turns`) goes to the model only in the
  no-documents path (fallback, around lines 89–107).
- **The context is glued-together questions.** `_prepare_sse_question_based_on_history` appends up to 4 previous
  user questions (`LAST_QUESTIONS_TO_QUERY = 4`, `chat/api.py:128`) to the text "The user previously asked about: … Now answer
  the question: …". That text goes to the search engine as a single query.
- There is a hidden option `use_intelligent_query_rewrite` (`message.py`, around line 270). An LLM rewrites the last question
  into a standalone one based on the 5 most recent messages. The model is hardcoded (`google/gemini-2.5-flash-lite`),
  the option is not described in the API and it does not change the fact that the answer-generating model does not see the history.

**Impact on the employee.**
1. "Expand point 2", "shorten it", "make a table", "translate" do not work: the model does not know its previous answer.
2. Glued questions blur the search. After a topic change in the conversation, fragments about old questions come back.
3. A question with a pronoun ("and how much does it cost?") depends on luck in the gluing.
4. The glued text is hardcoded in Polish, regardless of `lang`.

**Proposal.**
1. Pass the conversation history to the RAG answer model: questions and answers from the last N turns
   or within a token limit. Summarize older turns. New fragments from the search come in alongside the history.
2. Build the search query by rewriting the question into a standalone one (query rewrite), not by gluing.
   Take the rewriting model from configuration, not from the code. Return the rewritten query in the answer
   (`rewritten_query`) so the UI can show "Searched for: …".
3. Remember the conversation's sources. On a follow-up the model can cite fragments from previous answers.
   Footnote numbering is shared within a chat (with CR-01 and CR-02).
4. Recognize commands that do not require a new search ("shorten", "make a table", "translate").
   Answer from the history and its sources, with `answer_source: "history"` (an extension of CR-03).
5. The context also works after resuming a chat from history, after re-login and on another device.
   The state lives in the backend database, not in the frontend session.

**Acceptance criteria.**
- A 3-turn test scenario: "What obligations does the AI Act impose on providers?" → "Which of them apply to small firms?"
  → "Turn it into a table". The third answer is a table based on the second one's content, with footnotes.
- After a topic change in the chat, the search returns fragments about the new question, not the previous ones.
- After logging out and resuming the chat, follow-ups work the same as before logging out.
- The answer format is backwards compatible (new fields `rewritten_query`, `answer_source`).

**Transitional mode in the frontend.** The frontend cannot send the history to the model itself, because `add_user_message`
has no such parameter. For RadLab to decide: enable `use_intelligent_query_rewrite=true` in the MVP
(better search on follow-ups), if a rewriting model is available in their router.

---

## CR-01 · P0 · Footnotes: sentence → fragment → page (must have)

**Problem.** Fragments reach the model as `{document_name: [texts]}`
(`engine/controllers/search/semantic.py`, `convert_search_results_to_doc2answer`, around line 1306;
the call at `engine/controllers/models_logic/generative.py:248`). No numbers, pages or identifiers.
The model has nothing to cite, and the answer (`generative_answer`, `add_user_message`) does not return a list of used fragments.

**Proposal.**
1. Number the context fragments `[1]…[n]`. Each with the document name and page, e.g. `[3] (AI Act Report, p. 44) …text…`.
2. Add to the prompt (router / system template) the instruction: end every claim with a fragment number `[n]`,
   do not cite numbers outside the list.
3. Return in the `generative_answer` and `add_user_message` (and in `last_state`) answers the field:
   ```json
   "citations": [
     {"n": 3, "text_id": 1234, "document_id": 56, "document_name": "AI Act Report.pdf",
      "page_number": 44, "text_str": "…", "char_start": 120, "char_end": 410}
   ]
   ```
4. Validate on the backend: numbers in the answer ⊆ numbers in `citations`. Remove or mark unknown numbers.

**Acceptance criteria.**
- Every number `[n]` in the answer has an entry in `citations` with document and page.
- On the RadLab test set (e.g. `sse_tools/evaluation`) ≥ 90% of substantive sentences have a footnote.
- The answer format is backwards compatible (a new field, old ones unchanged).

**Transitional mode in the frontend.** `use_doc_names_in_response=true` + a `system_prompt` with an instruction to cite the
document name. The frontend matches the name against `detailed_results_json` and picks the page. The footnote is marked "approximate".

---

## CR-02 · P0 · Fragment identifiers and position in results

**Problem.** `detailed_results` (search and chat state) contains no `text_id` and no `document_id`
(`engine/core/search_engine.py`, around lines 552–593). The document preview (`document_content`) returns pages,
but a fragment cannot be pointed to within them.

**Proposal.**
- Add `text_id`, `document_id` and `char_start` / `char_end` relative to the `document_content` page text to every result.
- `document_content` optionally accepts `text_id` and returns the page with the range to highlight.

**Acceptance criteria.** Clicking a footnote opens the page and highlights exactly the quoted fragment.
The same fragment has the same `text_id` across successive queries, which enables deduplication by agents.

---

## CR-03 · P1 · Explicit marking of document-less answers

**Problem.** When RAG finds nothing, the chat silently answers with the bare model (`chat/controllers/message.py`, around lines 89–107).
The frontend infers this from empty results, which is fragile.

**Proposal.**
- Return the field `answer_source: "rag" | "llm_fallback"` in the `add_user_message` answer.
- Add the option `rag_only: true`: no fallback, with an explicit "no content" message depending on `lang`.
  Today the message is hardcoded in Polish.

**Acceptance criteria.** The frontend does not have to guess. With `rag_only` no answer without sources reaches the employee.

---

## CR-04 · P1 · Sources and footnotes stored with chat messages

**Problem.** `GET chats` and `GET get_chat_by_hash` return messages without state (`MessageSerializer`).
Sources and footnotes of older answers disappear after the session closes.

**Proposal.** Add an optional `with_sources=true` parameter to `chats` and `get_chat_by_hash`.
Then the `DeepMessageSerializer` with `rag_message_state`, shortened results and `citations` is returned.

**Acceptance criteria.** After re-login, every previous RAG answer has its footnotes and sources.

**Relation to CR-14.** CR-04 concerns what the employee sees on older answers. CR-14 concerns
what the model remembers. Both use the same source storage attached to the message.

---

## CR-05 · P1 · Chat management

**Problem.** `chats` returns all chats with all messages, without titles or pagination.
There is no deletion or renaming.

**Proposal.**
- `GET chats?limit=&offset=&light=true`: a list of `{chat_id, title, collection_name, created_at, updated_at, messages_count}`.
  Today `chats` does not return the chat's collection (`prepare_response_body`: only `chat_id`, `is_read_only`, `chat_history`),
  so after re-login the UI does not know which base the conversation took place in.
- An automatic title from the first question, with the possibility to change it via `POST rename_chat`.
- `POST delete_chat`.

**Acceptance criteria.** A list of 100 chats loads in < 500 ms. The employee can delete and rename a chat.

---

## CR-06 · P2 · Progress, streaming and stopping generation

**Problem.** `add_user_message` blocks for up to ~120 s without feedback.

**Proposal.** A streaming variant (SSE): events `searching` (document count), `found` (n fragments),
`generating`, successive tokens, `done` (the full answer with `citations`).

**Stopping generation.** `POST cancel_generation` (`chat_id`). The backend interrupts the search or the generation
and does not save an incomplete answer to history. Today interrupting on the UI side does not stop the backend,
so the answer later appears in history despite clicking "Stop".

**Acceptance criteria.** The first progress information in < 2 s. The frontend can show stages like in the benchmark (Elicit).
After "Stop" there is no interrupted answer in the chat history.

---

## CR-07 · P2 · Document metadata and downloading the original

**Problem.**
- No document date and version in results, so it is not possible to warn about outdated or conflicting versions (a gap from the benchmark).
- No downloading of the original file.

**Proposal.**
- `document_date`, `uploaded_at` and `file_type` in results and in `document_content`.
- The same fields plus the page count in `GET documents`. Today the list returns only names (`SimpleDocumentSerializer`),
  and the base content preview in the MVP shows only the name and the file type from the extension.
- `GET document_file?document_id=`: the file or a signed URL, respecting `delete_files_after_indexing`.

---

## CR-08 · P2 · Sharing a chat in the organisation

**Problem.** `get_chat_by_hash` returns the chat only to its owner, so a "share" link does not work for a colleague.

**Proposal.** A chat stored as read-only available to users of the same organisation or group,
provided they have access to the chat's collection.

---

## CR-09 · R · Async jobs API for agents

**Context.** The roadmap has agents that query the base many times to prepare material (a report, a note, a summary).
One blocking call of up to 120 s per step is not enough here.

**Proposal.**
- `POST agent_jobs` (goal, collections, time and query-count limits) → `job_id`.
- `GET agent_jobs/{id}`: status, stage, progress, partial result.
- `POST agent_jobs/{id}/cancel`.
- Modelled on the indexing queue (Celery + RabbitMQ, `IndexingJob`) – the infrastructure already exists.

---

## CR-10 · R · Batch search and deduplication

**Proposal.**
- `POST search_batch`: many `query_str` in one call, shared options.
- Results with `text_id` (CR-02), merged and deduplicated, with information on which query hit which fragment.

**Acceptance criteria.** An agent running 10 sub-queries gets one list of unique fragments with sources.

---

## CR-11 · R · Agent work trace and citations in long material

**Proposal.**
- Store a trace: plan → queries → found fragments → material sections → citations.
- Citations (CR-01) must be stable across steps. The same `text_id` gives the same footnote in the whole resulting document.
- Export of the material (Markdown/DOCX) with a bibliography: document, page.

**Acceptance criteria.** Every sentence of the generated material can be traced to a source fragment.

---

## CR-12 · R · Plan and clarifying questions

**Proposal.**
- A "plan" step returned before executing an agent task (a list of sub-queries and sources, editable by the user).
- A clarifying question with options when the goal is unclear (patterns from Gemini, Copilot and Unify in the benchmark).

---

## CR-18 · P1 · Document selection remembered with the chat

**Context.** In the MVP the employee selects the documents RAG should search (the NotebookLM pattern).
The frontend sends them in `search_options.documents` with every `add_user_message` – that works today.

**Problem.** The backend stores `search_options` with every message, but `MessageSerializer` does not return it,
and the chat has no scope of its own. After resuming a conversation from an earlier session the frontend does not know
which documents were selected and falls back to "all".

**Proposal.**
- The document scope stored with the chat: `POST set_chat_documents` (`chat_id`, `documents[]`) or a field in `new_chat`.
- `GET chats` returns `documents` for the chat. `add_user_message` without `search_options.documents` uses the chat's scope.
- When a document from the scope is removed from the base, the answer contains a `missing_documents` list.

**Acceptance criteria.** After re-login and opening the chat, the same documents as before logging out are selected.

---

## CR-19 · P1 · `system_prompt` merged with the template prompt

**Problem.** When a query matches the collection's question templates, the backend picks a template prompt at random and
**replaces** with it the `system_prompt` from the request (`chat/controllers/message.py`, `_prepare_rag_supervisor_state`, `template_prompts`).
The interface passes the answer format and the citation instruction in `system_prompt`, so in such collections
both stop working.

**Proposal.** Merge the prompts: first the template prompt, then the `system_prompt` from the request. Or a separate field
`answer_instructions`, always appended at the end of the prompt.

**Acceptance criteria.** In a collection with templates the answer has the chosen format and document names for footnotes.

---

## CR-15 · P2 · Refining the question before sending

**Problem.** Employees type short questions ("AI costs 2025"). RAG then searches broadly, and the answer is generic
or off target. In the benchmark, good tools help refine the question before searching
(Unify, Gemini; likewise the modes in Claude and tools like Prompt Cowboy).

**Proposal.**
- `POST refine_question` (`collection_name`, `question`, optionally `chat_id`) returns:
  ```json
  {"refined_question": "What costs of deploying AI tools were planned for 2025 in the budget reports?",
   "changes": ["added the period", "added the cost type"],
   "missing": [{"label": "Scope", "options": ["the whole company", "IT department", "pilot projects"]}]}
  ```
- The model takes into account the collection description, the document list and the chat history (CR-14).
- The call takes less than 3 s (a small model). It can be based on the existing `_rewrite_query_with_llm` mechanism.

**How it looks in the UI.** For a short or generic question, a "Refined question" suggestion appears under the field.
The employee accepts it, edits it, or sends their own version unchanged. Nothing happens without their consent.

**Acceptance criteria.** On the RadLab test set, answers to refined questions are rated higher
than answers to the original ones. The employee can always send the question unchanged.

**Relation.** CR-12 (agents' clarifying questions) can use the same endpoint.

---

## CR-16 · P1 · Sections in the history and pinning conversations

**Problem.** The history is a flat list of chats. An employee juggling several topics at once (a report, a tender, regulations)
has no way to organize them. Pattern: sections and projects in Claude.

**Proposal.**
- `GET chat_groups`, `POST chat_groups` (`name`), `POST rename_chat_group`, `POST delete_chat_group`
  (chats go back to "No section").
- `POST move_chat` (`chat_id`, `group_id`); `GET chats?group_id=` (together with CR-05).
- `POST pin_chat` (`chat_id`, `pinned`); `GET chats` returns `group_id` and `pinned` for every chat.
- `new_chat` optionally accepts `group_id` (the "+" button next to a section).
- Section order: `POST reorder_chat_groups` (later, for drag-and-drop).
- Optionally: a default collection per section (a new chat in a section starts with its knowledge base).

**UI state.** The sections are designed and working in the prototype (the Claude Code pattern: a section header with collapsing and "+",
a ⋯ menu next to a conversation: Pin, Rename, Move to section, Delete). The frontend will enable them with the `features.chat_sections`
flag after this request and CR-05 are implemented. Priority raised from P2 to P1 by the 2026-11-01 decision.

**Acceptance criteria.** The employee creates a section, moves a chat into it, pins a chat, and after re-login
sees the same history layout.

---

## CR-17 · R · Notes from answers for reuse

**Problem.** Good answers get lost in history. The employee wants to gather fragments with footnotes
from several conversations and use them in another task (the NotebookLM pattern).

**Proposal.**
- `POST notes` (`chat_id`, `message_id`, `text` – the whole answer or a selected fragment, `citations[]`, optionally `group_id`).
- `GET notes` (filtered by the section from CR-16), `POST update_note`, `POST delete_note`.
- A note keeps its footnotes (`text_id` from CR-02), so it can be verified at the source even a month later.
- `add_user_message` optionally accepts `note_ids[]`. Note contents enter the model context alongside the search results.
- Agents (CR-09) accept notes as input material.

**Acceptance criteria.** The employee saves an answer fragment as a note, opens it later with footnotes
and asks a question with that note as context.

**Dependencies.** CR-01, CR-02, CR-14.

---

## CR-13 · later · PPTX, XLSX, CSV

Deferred by the 2026-11-01 decision. To be taken up after the MVP fixes: file readers and a representation of tabular data
(a row/sheet as the source of a footnote).
