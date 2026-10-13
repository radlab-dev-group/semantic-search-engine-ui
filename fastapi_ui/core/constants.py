MAX_VAL_RATING_GENERATIVE_ANSWER = 5

# Default configuration path (can be overridden with UI_CONFIG_PATH env variable)
CONFIGS_DIR = "configs"
DEFAULT_CONFIG_PATH = "ui-configuration.json"

# Search form defaults (mirrors Streamlit ui_utils.prepare_search_params)
DEFAULT_MAX_RESULTS = 25
MAX_RESULTS_LIMIT = 100
DEFAULT_PERC_RANK_TO_GEN_QA = 40

# Generative model defaults (mirrors Streamlit generation options)
DEFAULT_TOP_K = 50
DEFAULT_TOP_P = 0.95
DEFAULT_TEMPERATURE = 0.65
DEFAULT_TYPICAL_P = 1.0
DEFAULT_REPETITION_PENALTY = 1.1
DEFAULT_MAX_NEW_TOKENS = 1024
MAX_MAX_NEW_TOKENS = 4000

# Answer languages available for translation
ANSWER_LANGUAGES = ["pl", "en-us", "en-gb", "de", "cs"]

# Embedder index types available for new collections
INDEX_TYPES = ["IVF_FLAT", "HNSW"]

# Upload indexing defaults (mirrors Streamlit 2_Upload_Documents.py)
DEFAULT_MAX_TOKENS_IN_CHUNK = 200
MAX_TOKENS_IN_CHUNK_LIMIT = 1000
DEFAULT_OVERLAP_TOKENS = 20
OVERLAP_TOKENS_LIMIT = 200

# Accepted file types for document upload
ACCEPTED_FILE_EXTENSIONS = [".pdf", ".docx", ".txt", ".html", ".md", ".zip"]
