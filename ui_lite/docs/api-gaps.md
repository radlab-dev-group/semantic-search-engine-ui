# semantic-search-engine API gaps – RAG chat for employees

November 1, 2026 · based on the backend code at commit 58c0b8d (2026-10-30)

The frontend runs on today's API. The gaps below limit it or force workarounds.
**Must have** means P0 items: without them we cannot meet two main requirements – a footnote that points
to the right place in a document, and a conversation in which the model remembers what was said.

Priorities: **P0** – must have · **P1** – important for the MVP · **P2** – next version.

## List of gaps

Endpoints and fields that do not exist today but that the interface already anticipates. "MVP" means the element is in the MVP
in a transitional form (with a visible limitation) or hidden behind a flag until the change lands.

| # | What is missing (endpoint / field) | UI element that needs it | Until the change | CR | Priority |
|---|---|---|---|---|---|
| 1 | Conversation history (questions **and answers**) passed to the model that generates the RAG answer; `rewritten_query` field | follow-up questions ("expand", "make a table"), "Show as:" without a new search | the model only sees the 4 previous questions appended to the search | CR-14 | **P0** |
| 2 | Numbered fragments in the prompt and a `citations[]` field (`n`, `text_id`, `document_name`, `page_number`, `char_start`, `char_end`) in `add_user_message` | [n] footnotes next to sentences | approximate footnote: document certain, page chosen | CR-01 | **P0** |
| 3 | `text_id`, `document_id`, `char_start`, `char_end` in `detailed_results_json`; `document_content?text_id=` | quote highlighting in the document preview | searching for the quote text in the page content on the frontend | CR-02 | **P0** |
| 4 | `answer_source: "rag" \| "llm_fallback"` in `add_user_message`; the `rag_only` option | the "I didn't find this in the documents" warning | inferring it from an empty `detailed_results_json` | CR-03 | P1 |
| 5 | `GET chats?with_sources=true` – message state (sources, `sse_answer.id`) | sources, footnotes and rating for older answers | "sources unavailable" message + "Ask again" | CR-04 | P1 |
| 6 | In `GET chats`: `title`, **`collection_name`**, `created_at`, `updated_at`, `messages_count`, pagination (`limit`, `offset`) | history: title, date, conversation base, fast loading | title = first question; the base of a resumed conversation is only known in the current frontend session | CR-05 | P1 |
| 7 | `POST rename_chat`, `POST delete_chat` | the ⋯ menu next to a conversation: Rename, Delete | hidden (flag `features.chat_sections`) | CR-05 | P1 |
| 8 | `GET/POST chat_groups`, `rename_chat_group`, `delete_chat_group`, `POST move_chat`, `POST pin_chat`, `group_id` in `new_chat`, `group_id` and `pinned` in `chats` | sections in the history, pinning, "+" new chat in a section | hidden (flag `features.chat_sections`) | CR-16 | P1 |
| 9 | Document scope stored with the chat; `documents` in `GET chats` | the Documents panel after resuming a conversation | after resuming, the scope falls back to "all", with a message | CR-18 | P1 |
| 10 | `POST cancel_generation` (`chat_id`) | the "Stop" button | only stops waiting in the UI; the answer may still appear in history | CR-06 | P2 |
| 11 | Progress events / streaming (SSE) from `add_user_message` | stages "searching / found / writing", live text | a seconds counter | CR-06 | P2 |
| 12 | In `GET documents`: `document_date`, `uploaded_at`, `file_type`, `total_pages` | Documents panel: date, page count | only the name and the type taken from the extension | CR-07 | P2 |
| 13 | `system_prompt` from the request merged with the question-template prompt instead of overwritten | answer format (Brief / Bullet points / Detailed / Table), the citation instruction | in collections with templates the format and footnotes may not work | CR-19 | P1 |

Outside the MVP (roadmap): downloading the original file (CR-07), sharing inside the organisation (CR-08), agents (CR-09…12),
question refinement (CR-15), notes (CR-17), PPTX/XLSX/CSV (CR-13).

The full description of each request (problem, proposal, acceptance criteria) is in
[radlab-change-requests.md](radlab-change-requests.md).
