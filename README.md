# Semantic Search Engine UI

This repository provides a modern web interface for the
**[semantic‑search‑engine](https://github.com/radlab-dev-group/semantic-search-engine)**,
built with **FastAPI** and **Jinja2** templates.

It provides data preparation, collection and document management, semantic vector search,
hybrid search, generative question answering (RAG) with user rating, and search history.

## Getting Started

### Installation and Launch

```bash
cd fastapi_ui
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
bash run.sh                     # launches on http://localhost:8000
```

Alternatively, you can launch the application directly with Uvicorn:

```bash
cd fastapi_ui
uvicorn server:app --host 0.0.0.0 --port 8000
```

### Environment Variables

| Variable | Default | Description |
| --- | --- | --- |
| `UI_HOST` | `0.0.0.0` | Uvicorn host / listen address |
| `UI_PORT` | `8000` | Uvicorn port |
| `UI_CONFIG_PATH` | `configs/ui-configuration.json` | Path to API backend configuration file |
| `UI_SECRET_KEY` | `change-me-in-production` | Secret key used to sign session cookies |
| `UI_MAX_UPLOAD_SIZE_MB` | `6000` | Maximum size per uploaded file (in MB) |
| `UI_MAX_UPLOAD_FILES` | `500` | Maximum number of files in a single upload request |
| `UI_DEFAULT_LANGUAGE` | `en` | Fallback interface language (`en` or `pl`) |

### Backend Configuration

Backend endpoint URLs and hosts are configured in `configs/ui-configuration.json` (or the path set via `UI_CONFIG_PATH`).
Endpoints added later (`api/indexing_status`, `api/search_history`, …) fall back
to their default path when the configuration file does not list them, so an old
file keeps working.

## Key Features

- **Knowledge Base Management**:
  - Create, view, and delete collections. A new collection may declare its chunking (`max_tokens_in_chunk`, `number_of_overlap_tokens`, prefilled with the engine `chunking_defaults`) and `strict_chunking`; the chunk size is capped by `max_model_length` of the chosen embedder (`models_info`). Collection cards show the declared chunking and a `strict` badge.
  - Manage documents, toggle document visibility in search, and inspect/delete text chunks.
  - Upload multiple file formats (`.pdf`, `.docx`, `.txt`, `.html`, `.md`, `.zip`) or paste raw text, split with the settings of the collection or with custom chunking; the engine errors `CHUNKING_TOO_LONG` (`000005_DATA`) and `CHUNKING_MISMATCH` (`000006_DATA`) are shown inline on the form.
  - **Indexing progress** (`GET api/indexing_status`): a panel shows how many documents are indexed, which one the worker is embedding, how many are still waiting and which ones failed; document rows carry a status badge. Indexing runs inside the request or in a Celery + RabbitMQ queue on the engine side (`ENV_USE_CELERY=1`) — the panel looks the same, it just moves on its own.
- **Semantic & Hybrid Search**:
  - Vector similarity search with cosine similarity scoring.
  - Hybrid search (RRF) combining vector search and full-text keyword retrieval.
  - Result reranking with dedicated reranker models.
  - Generative QA: asynchronous answer generation based on retrieved passages, with multi-star rating and user feedback.
  - Search history per collection with pre-filled filters and parameters.
- **Modern UI & UX**:
  - Lightweight, responsive design without external CDN dependencies (works fully offline).
  - Dark / Light / Auto theme support.
  - Bilingual interface (Polish and English) with runtime locale switching (`EN | PL`).
  - OpenAPI documentation available at `/docs` and health check at `/healthz`.

## Testing

Smoke tests run against a local mock backend (`tests/mock_sse_backend.py`) and validate all views, authentication, search flows, and localization:

```bash
cd fastapi_ui
.venv/bin/pip install httpx
.venv/bin/python tests/smoke_test.py
```

For more details on application architecture, endpoints, and components, see [`fastapi_ui/README.md`](fastapi_ui/README.md).
