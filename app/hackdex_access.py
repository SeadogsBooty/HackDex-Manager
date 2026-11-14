"""Backend network access is opt-in only after upstream authorization."""
import os


def upstream_enabled():
    return os.environ.get("HACKDEX_UPSTREAM_ACCESS", "").strip().lower() == "authorized"


LOCAL_ONLY_MESSAGE = (
    "Local-only mode: automated HackDex access is disabled. "
    "Use existing catalog data and permitted cached patches, or the official website. "
    "Enable HACKDEX_UPSTREAM_ACCESS=authorized only after obtaining authorization."
)
