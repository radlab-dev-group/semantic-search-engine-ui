## Description

This repository provides a view for the
**[semantic‑search‑engine](https://github.com/radlab-dev-group/semantic-search-engine)**.  
Its individual components (the `pages`) are used to prepare data for indexing.

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