MAX_VAL_RATING_GENERATIVE_ANSWER = 5

# Default configuration path (can be overridden with UI_CONFIG_PATH env variable)
CONFIGS_DIR = "configs"
DEFAULT_CONFIG_PATH = "ui-configuration.json"

# Search form defaults
DEFAULT_MAX_RESULTS = 8
MAX_RESULTS_LIMIT = 100
DEFAULT_PERC_RANK_TO_GEN_QA = 100
# Cosine similarity cutoff of the vector search (search option
# "min_similarity", a number in [0, 1]); the chunks scoring below are dropped.
# Mirrors DEFAULT_MIN_SIMILARITY of the engine, which is used when the option
# is missing or invalid. 0 disables the cutoff.
DEFAULT_MIN_SIMILARITY = 0.5

# Generative model defaults
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

# Chunking sliders of the indexing forms. The values the engine actually uses
# come from the collection (metadata_json) or from GET filter_options
# (chunking_defaults); DEFAULT_* only place the sliders when neither is known,
# and *_LIMIT is the slider range (stretched when the collection asks for more).
DEFAULT_MAX_TOKENS_IN_CHUNK = 400
MAX_TOKENS_IN_CHUNK_LIMIT = 1000
DEFAULT_OVERLAP_TOKENS = 60
OVERLAP_TOKENS_LIMIT = 200

# Accepted file types for document upload
ACCEPTED_FILE_EXTENSIONS = [".pdf", ".docx", ".txt", ".html", ".md", ".zip"]
