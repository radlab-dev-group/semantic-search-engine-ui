## Description

This repository provides a view for the
**[semantic‑search‑engine](https://github.com/radlab-dev-group/semantic-search-engine)**.  
Its individual components (the `pages`) are used to prepare data for indexing.

Two UI implementations are available:

| Application | Stack | Directory |
| --- | --- | --- |
| Streamlit UI (original) | `streamlit` | `streamlit_ui/` |
| FastAPI UI (twin, server-side templates) | `fastapi` + `jinja2` | `fastapi_ui/` |

Both talk to the same REST API (login with a Django token, collections, uploads,
search with options, generative answers with rating, conversational search) and
share the same configuration file layout (`configs/ui-configuration.json`).

### Streamlit application

The `streamlit_ui/` directory contains the source code for the UI of the semantic search (RAG) engine and the
conversational search model.  
To start the application, run the `run.sh` script:

```textmate
cd streamlit_ui
bash run.sh
```

#### Contents of `run.sh`

```textmate
#!/bin/bash

# Run the application under the Streamlit server
export STREAMLIT_SERVER_MAX_UPLOAD_SIZE=5000   # maximum upload size per file (in MB)

# LLama2 configuration
export SHOW_LLAMA_70B_MODEL=true   # set to true to enable the 70‑billion‑parameter LLama2 model

# Launch the app
streamlit run Home.py
```

* `STREAMLIT_SERVER_MAX_UPLOAD_SIZE` controls the maximum size of a single file that can be uploaded for indexing. It is
  set to **5 GB** (5000 MB).
* `SHOW_LLAMA_70B_MODEL` toggles the 70 B LLama2 model on or off. To disable this model, comment out (or remove) the
  line that exports this variable.

### FastAPI application

The `fastapi_ui/` directory contains the same features implemented with FastAPI and
Jinja2 templates (no client-side JS framework, session stored in a signed cookie).

```bash
cd fastapi_ui
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
bash run.sh                     # http://localhost:8000
```

Page mapping, environment variables and the list of behavioural differences are
described in [`fastapi_ui/README.md`](fastapi_ui/README.md).
