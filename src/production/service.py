"""Production service — orchestration layer for compiled IR execution.

Thin orchestration delegating to compiler, optimizer, executor, and cache.
"""

from __future__ import annotations

from .cache import IRCache, get_ir_cache, reset_ir_cache
from .compiler import RuleCompiler, compile_rule, compile_rules
from .executor import RuleRuntime, execute_rule
from .optimizer import RuleOptimizer, optimize_rule
from .premise_index import PremiseIndexBuilder, get_premise_index, reset_premise_index
from .schemas import RuleIR
from .trace import DecisionResult, ExecutionTrace

__all__ = [
    # Compiler
    "RuleCompiler",
    "compile_rule",
    "compile_rules",
    # Optimizer
    "RuleOptimizer",
    "optimize_rule",
    # Executor
    "RuleRuntime",
    "execute_rule",
    # Cache
    "IRCache",
    "get_ir_cache",
    "reset_ir_cache",
    # Premise Index
    "PremiseIndexBuilder",
    "get_premise_index",
    "reset_premise_index",
    # IR Types
    "RuleIR",
    # Trace
    "DecisionResult",
    "ExecutionTrace",
]
