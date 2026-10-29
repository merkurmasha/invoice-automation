"""Settings for the extraction module.

Keeping the model name here, and nowhere else, means switching models
later is a one-line change.
"""

from pathlib import Path

# The only place the Claude model name should appear in this project.
MODEL_NAME = "claude-haiku-5-5"

# Where extraction results are cached on disk, keyed by file contents + model.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / "data" / "cache"

# Fields extracted with confidence below this are considered "low confidence"
# by later phases (not enforced here — extraction just reports the number).
CONFIDENCE_THRESHOLD = 0.80
