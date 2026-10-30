"""Settings for the supplier-categorisation module.

Styled the same way as src/extract/config.py (model name + prompt
version + cache dir + confidence threshold, all in one place) but kept
as its own file rather than added to that one, so this phase never
edits extraction's files.
"""

from pathlib import Path

# Same cheap model as extraction (src/extract/config.py's MODEL_NAME) —
# categorisation is a simple classification job, not transcription, so
# there's no reason to reach for anything bigger.
CATEGORISE_MODEL = "claude-haiku-5-5"

# Bumped whenever the system prompt in categorise.py changes meaningfully.
# Part of the cache key, so a prompt change naturally misses the cache
# instead of silently reusing a result categorised under old wording.
CATEGORISE_PROMPT_VERSION = "v1"

# Shared with extraction's cache dir — safe because cache keys are
# content hashes that already include which module produced them
# (categorise.py salts its key differently from extract.py's), so the
# two can never collide.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

# A categorisation below this confidence is routed to the review queue
# instead of being trusted outright.
CATEGORY_CONFIDENCE_THRESHOLD = 0.80
