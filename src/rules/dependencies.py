"""Rules domain dependency injection."""

import contextlib

from src.config import get_settings
from src.rules.service import DecisionEngine, RuleLoader

_loader: RuleLoader | None = None
_engine: DecisionEngine | None = None


def get_loader() -> RuleLoader:
    """Get or create the rule loader instance."""
    global _loader
    if _loader is None:
        settings = get_settings()
        _loader = RuleLoader(settings.rules_dir)
        with contextlib.suppress(FileNotFoundError):
            _loader.load_directory()
    return _loader


def get_engine() -> DecisionEngine:
    """Get or create the decision engine instance."""
    global _engine
    if _engine is None:
        _engine = DecisionEngine(get_loader())
    return _engine


def reset_loader() -> None:
    """Reset loader and engine (e.g., after rule reload)."""
    global _loader, _engine
    _loader = None
    _engine = None
