import os

from pages.src.config import SessionConfig
from pages.src.env_utils import bool_env_value
from pages.src.api import SemanticSearchEngineAPI


session_config = SessionConfig()
sse_api_engine = SemanticSearchEngineAPI()

MAX_VAL_RATING_GENERATIVE_ANSWER = 5

SSL_CONNECTION = bool_env_value("STREAMLIT_SSL_CONNECTION")
RUN_SERVER_LOCALHOST = bool_env_value("STREAMLIT_RUN_SERVER_LOCALHOST")
