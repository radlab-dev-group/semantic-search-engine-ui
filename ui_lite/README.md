# Employee RAG chat – frontend for `semantic-search-engine`

A minimalist web interface where an employee asks questions of the company knowledge base
and gets an answer with footnotes pointing to the document page.
Runs on the existing RadLab backend [`semantic-search-engine`](https://github.com/radlab-dev-group/semantic-search-engine)
(verified against the code at commit `58c0b8d`, 2026-10-30). It does not need backend changes to start.
Some features run in a transitional mode until the changes described in [docs/radlab-change-requests.md](docs/radlab-change-requests.md) land.

Version 0.1.0 · role: employee (no collection management) · web on a computer only · PL/EN · light and dark mode.

## What it does

- Local login or a company account (Keycloak/OAuth through the backend).
- Choosing a knowledge base; a new chat starts with the last used one.
- The Documents panel: the list of the base's documents, checkboxes and "Select all" – RAG only searches in the selected ones.
- Chat with follow-up questions; a waiting counter and "Stop".
- Answer format: Brief / Bullet points / Detailed / Table, with "Show as:".
- [n] footnotes next to sentences (approximate for now), sources grouped by document, a coverage line.
- Document text preview from the footnote page, with the quoted fragment highlighted and the following pages.
- 👍/👎 rating with a comment, "Copy", "Copy with sources".
- Conversation history and resuming a conversation.
- Explicit messages: no sources in the documents, time exceeded, no access, expired session, service unavailable.

## Quick start

```bash
cp configs/ui-configuration.example.json configs/ui-configuration.json   # and fill it in
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --port 8000
.venv/bin/pytest -q
```

## Configuration

The file `configs/ui-configuration.json` (the path can be changed with `UI_CONFIG`). The format of the `api_hosts`
section is compatible with the current RadLab UI `ui-configuration.json`. Example: [configs/ui-configuration.example.json](configs/ui-configuration.example.json).

| Section / variable | What it sets |
|---|---|
| `api_hosts.semantic_search_engine.host` / `SSE_API_HOST` | the backend address |
| `…prefix` / `SSE_API_PREFIX` | the API prefix (`api` or `api/v1`) |
| `…ep` | endpoint names, in case a deployment renames them |
| `auth.mode` / `AUTH_MODE` | `local` (a form) or `sso` (SSO button only); `auth.sso_button` adds an SSO button in `local` mode |
| `SESSION_SECRET` | **required in production** – the session cookie signing key |
| `SESSION_HTTPS_ONLY` | `true` behind HTTPS |
| `defaults.options` | generation options sent with every `new_chat` and `add_user_message`; empty `generative_model` = the first from `GET generative_models` |
| `defaults.search_options` | search options (result count, hybrid, reranking, similarity threshold) |
| `defaults.document_preview_pages` | how many pages the document preview fetches at once |
| `citation_instruction` | the model instruction to give the document name after sentences (the basis for approximate footnotes) |
| `formats[]` | answer formats: PL/EN labels, `system_prompt`, `max_new_tokens`; `default_format` |
| `features.chat_sections` | sections in the history – keep `false` until CR-16 and CR-05 |
| `timeouts` | GET 30 s, `add_user_message` 150 s |
| `ui.history_limit` | how many conversations to show before "Show more" |

**SSO.** The button calls `POST login_url` and redirects to Keycloak. The return address that must be set
in the Keycloak client/backend: `https://<frontend-address>/login/callback`. The frontend exchanges `code` and `state`
for a token through `POST login` and refreshes it through `POST refresh_token` after a 401 response.

## How it works

The browser only talks to the frontend server (`/ui-api/*`). The server calls the backend with the session token,
so the backend does not need CORS and the token does not reach the JavaScript code (an `HttpOnly`, signed cookie).

### Endpoint map

| UI element | Frontend route | Backend endpoint |
|---|---|---|
| Local login | `POST /login` | `POST login` (`username`, `password`) |
| SSO login | `GET /login/sso`, `GET /login/callback` | `POST login_url`, `POST login` (`code`, `state`, `session_state`), `POST refresh_token` |
| Knowledge bases | `GET /ui-api/collections` | `GET collections` |
| Documents | `GET /ui-api/documents` | `GET documents` (`collection_name`) |
| Question | `POST /ui-api/ask` | `POST new_chat` (first question), `POST add_user_message` (follow-ups) |
| Generative model | (from `ask`) | `GET generative_models` (once, if `generative_model` is empty in the configuration) |
| Footnotes and sources | (from `ask`) | `last_state[0].rag_message_state.sse_response.detailed_results_json` |
| Document preview | `GET /ui-api/document` | `GET document_content` (`from_page`, `max_pages`, `next_page`) |
| Rating | `POST /ui-api/rate` | `POST rate_generative_answer` (`answer_response_id` = `sse_answer.id`, `rate_value` 0/1, `rate_value_max` 1) |
| History | `GET /ui-api/chats`, `GET /ui-api/chats/{id}` | `GET chats` |
| The "service unavailable" banner | `GET /ui-api/health` | `GET healthz` |
| Copy, copy with sources, theme, language | – | frontend only (`lang` is sent with every call) |

### Approximate footnotes (until CR-01)

The backend passes fragments to the model as `{document_name: [texts]}`, without numbers and pages.
The frontend asks the model (`citation_instruction`) to put the document name in square brackets after a sentence,
matches those names against `detailed_results_json` ([app/core/answers.py](app/core/answers.py)) and uses the best-scoring
fragment page from that document as the footnote page. The footnote has a dashed border and the note
"the page may be approximate". If the model does not give the names, a source list remains under the answer.

## API gaps that need to be filled

The full list with acceptance criteria: [docs/radlab-change-requests.md](docs/radlab-change-requests.md) (the "API gaps" section).

| Priority | What is missing | CR |
|---|---|---|
| P0 | Conversation history (questions and answers) passed to the model generating the RAG answer | CR-14 |
| P0 | Numbered fragments and a `citations[]` field in the answer | CR-01 |
| P0 | `text_id`, `document_id`, `char_start/end` in results; `document_content?text_id` | CR-02 |
| P1 | `answer_source` and the `rag_only` option | CR-03 |
| P1 | `chats?with_sources=true` | CR-04 |
| P1 | In `chats`: `title`, `collection_name`, dates, pagination; `rename_chat`, `delete_chat` | CR-05 |
| P1 | Sections and pinning: `chat_groups`, `move_chat`, `pin_chat` | CR-16 |
| P1 | The document scope stored with the chat | CR-18 |
| P1 | `system_prompt` merged with the question-template prompt, not overwritten | CR-19 |
| P2 | `cancel_generation`, progress / streaming | CR-06 |
| P2 | Date, type and page count in `documents` | CR-07 |

## Security and deployment

- The session is a signed `HttpOnly`, `SameSite=Lax` cookie; set `SESSION_HTTPS_ONLY=true` behind HTTPS.
- Model answers are rendered from Markdown with HTML disabled, so the model cannot inject a script.
- Fonts (Inter, Newsreader – SIL OFL 1.1) are in the repo; the page does not connect to external servers.
- **Scaling:** the frontend keeps answer sources and the conversation base in process memory (`app/core/session_store.py`),
  because the backend does not return them in history (CR-04, CR-05). Run a single process or sticky sessions;
  with several replicas replace `MemoryStore` with Redis (the `SessionStore` interface).
- The proxy in front of the frontend must allow requests of up to 150 s (`/ui-api/ask`).

## Structure

```
app/
  main.py               – the FastAPI application
  core/config.py        – configuration (JSON + environment variables)
  core/api_client.py    – backend calls, envelope, error mapping
  core/answers.py       – footnotes, source grouping, Markdown
  core/session_store.py – memory for sources and conversation metadata
  routes/               – login, pages, /ui-api
  templates/, static/   – HTML, CSS (RadLab tokens), JS, fonts
  locales/              – PL and EN texts
tests/                  – footnote-logic tests and contract tests
docs/                   – change requests for RadLab, architectural decisions (ADRs)
```
