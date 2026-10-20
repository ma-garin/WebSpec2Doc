"""WebSpec2Doc Native Accessibility Checker（自社実装。外部 JS を注入しない）。"""

from __future__ import annotations

from .catalog import CATALOG, CATALOG_BY_ID, LEGACY_TO_NATIVE
from .models import (
    CATALOG_VERSION,
    ENGINE_NAME,
    A11yViolation,
    Finding,
    Implementation,
    Level,
    NodeResult,
    PageA11yResult,
    RuleResult,
    RuleSpec,
    Status,
    aggregate_rule,
    aggregate_status,
    build_page_result,
    to_legacy_violations,
    ui_group,
)

__all__ = [
    "CATALOG", "CATALOG_BY_ID", "LEGACY_TO_NATIVE", "CATALOG_VERSION", "ENGINE_NAME",
    "A11yViolation", "Finding", "Implementation", "Level", "NodeResult", "PageA11yResult",
    "RuleResult", "RuleSpec", "Status", "aggregate_rule", "aggregate_status",
    "build_page_result", "to_legacy_violations", "ui_group",
]
