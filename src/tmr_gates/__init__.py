"""tmr-gates: the publication gates of The Machine Record as a standalone package."""
from .config import DEFAULTS, Config, default_config
from .gates import (
    COURT_NON_BLOCKING,
    Decision,
    check_is_incident,
    check_robot_subject,
    court_document,
    evaluate,
    independent_domains,
    material_disagreements,
    min_score,
    precheck_sources,
    precheck_verification,
    required_domains,
    strip_private_names,
)
from .tiers import GOV_SUFFIXES, TIER1_DOMAINS, TIER3_DOMAINS, TIER3_HINTS, tier_of

__version__ = "0.1.0"
__all__ = [
    "COURT_NON_BLOCKING", "DEFAULTS", "Config", "Decision", "GOV_SUFFIXES", "TIER1_DOMAINS",
    "TIER3_DOMAINS", "TIER3_HINTS", "check_is_incident", "check_robot_subject", "court_document",
    "default_config", "evaluate", "independent_domains", "material_disagreements", "min_score",
    "precheck_sources", "precheck_verification", "required_domains", "strip_private_names",
    "tier_of",
]
