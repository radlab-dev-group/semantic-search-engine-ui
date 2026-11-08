#!/bin/bash

# Run the FastAPI UI under Uvicorn.

cd "$(dirname "$0")" || exit 1

export UI_HOST="${UI_HOST:-0.0.0.0}"          # listen address
export UI_PORT="${UI_PORT:-8123}"             # listen port
export UI_CONFIG_PATH="${UI_CONFIG_PATH:-configs/ui-configuration.json}"
export UI_SECRET_KEY="${UI_SECRET_KEY:-change-me-in-production}"
export UI_MAX_UPLOAD_SIZE_MB="${UI_MAX_UPLOAD_SIZE_MB:-6000}"  # per uploaded file
export UI_MAX_UPLOAD_FILES="${UI_MAX_UPLOAD_FILES:-500}"

#if [ -x ".venv/bin/uvicorn" ]; then
#  UVICORN=".venv/bin/uvicorn"
#else
#  UVICORN="uvicorn"
#fi

UVICORN="uvicorn"

exec "${UVICORN}" server:app --host "${UI_HOST}" --port "${UI_PORT}"
