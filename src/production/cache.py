"""In-memory cache for compiled rule IR.

Provides fast access to compiled rules, reducing database lookups.

From Workbench storage/retrieval/runtime/cache.py.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

    from .schemas import RuleIR


class IRCache:
    """Thread-safe in-memory cache for RuleIR objects."""

    def __init__(self, max_size: int = 1000) -> None:
        self._cache: dict[str, RuleIR] = {}
        self._max_size = max_size
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, rule_id: str) -> RuleIR | None:
        """Get a rule IR from cache."""
        with self._lock:
            if rule_id in self._cache:
                self._hits += 1
                return self._cache[rule_id]
            self._misses += 1
            return None

    def put(self, rule_id: str, ir: RuleIR) -> None:
        """Put a rule IR in cache."""
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._evict()
            self._cache[rule_id] = ir

    def invalidate(self, rule_id: str) -> bool:
        """Invalidate a cached rule."""
        with self._lock:
            if rule_id in self._cache:
                del self._cache[rule_id]
                return True
            return False

    def invalidate_all(self) -> int:
        """Invalidate all cached rules."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            return count

    def get_or_load(
        self,
        rule_id: str,
        loader: Callable[[str], RuleIR | None],
    ) -> RuleIR | None:
        """Get from cache or load using provided loader."""
        ir = self.get(rule_id)
        if ir is not None:
            return ir

        ir = loader(rule_id)
        if ir is not None:
            self.put(rule_id, ir)

        return ir

    def preload(self, rules: list[RuleIR]) -> int:
        """Preload multiple rules into cache."""
        with self._lock:
            count = 0
            for ir in rules:
                if len(self._cache) < self._max_size:
                    self._cache[ir.rule_id] = ir
                    count += 1
            return count

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = self._hits / total if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "cached_rules": list(self._cache.keys()),
            }

    def _evict(self) -> None:
        """Evict half of the cached entries (FIFO)."""
        keys = list(self._cache.keys())
        evict_count = len(keys) // 2
        for key in keys[:evict_count]:
            del self._cache[key]

    def contains(self, rule_id: str) -> bool:
        """Check if a rule is cached."""
        with self._lock:
            return rule_id in self._cache


# Global cache instance
_global_cache: IRCache | None = None


def get_ir_cache() -> IRCache:
    """Get or create the global IR cache."""
    global _global_cache
    if _global_cache is None:
        _global_cache = IRCache()
    return _global_cache


def reset_ir_cache() -> None:
    """Reset the global IR cache."""
    global _global_cache
    _global_cache = None
