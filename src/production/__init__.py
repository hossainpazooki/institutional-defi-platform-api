"""Production domain — compiled IR execution engine.

Merges:
- Workbench storage/retrieval/compiler/ (RuleCompiler, optimizer, premise index, IR)
- Workbench storage/retrieval/runtime/ (executor, cache, trace)
- Workbench core/api/routes_production.py (v2 API endpoints)
"""

from .cache import IRCache, get_ir_cache, reset_ir_cache
from .compiler import RuleCompiler, compile_rule, compile_rules
from .executor import RuleRuntime, execute_rule
from .optimizer import RuleOptimizer, optimize_rule
from .premise_index import PremiseIndexBuilder, get_premise_index, reset_premise_index
from .router import router
from .schemas import (
    CompiledCheck,
    CompileRequest,
    CompileResponse,
    DecisionEntry,
    EvaluateRequest,
    EvaluateResponse,
    ObligationSpec,
    RuleIR,
)
from .trace import DecisionResult, ExecutionTrace, TraceStep

__all__ = [
    # Router
    "router",
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
    "CompiledCheck",
    "DecisionEntry",
    "ObligationSpec",
    # Trace
    "ExecutionTrace",
    "TraceStep",
    "DecisionResult",
    # API Schemas
    "CompileRequest",
    "CompileResponse",
    "EvaluateRequest",
    "EvaluateResponse",
]
