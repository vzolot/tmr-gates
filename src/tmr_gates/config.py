"""Thresholds the gates read. The Machine Record keeps the live values in a
database table so its circuit breaker can switch auto-publishing off without a
deploy; this package only needs a mapping with the same keys.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DEFAULTS: dict[str, Any] = {
    # Kill switch: when False, evaluate() never returns publish=True.
    "auto_publish": True,
    # Minimum cross-verification score from the model for press sources.
    "min_verification_score": 0.80,
    # A lone court document with full text is a primary record; lower bar.
    "court_min_verification_score": 0.75,
    # Maximum risk score from the adversarial pass for press sources.
    "max_risk_score": 0.35,
    # Court documents are allowed a higher risk score because the "accusation"
    # is the filing itself, attributed and on the record.
    "court_max_risk_score": 0.75,
    # Local press in a language other than English (editorial decision of
    # 2026-10-25): a one-outlet account of a plant accident in Gunma reads as
    # riskier to the adversarial pass than a wire story, although the facts are
    # the same kind. Still two independent domains, still the grave rule, but
    # the risk ceiling sits between press and court records.
    "foreign_max_risk_score": 0.5,
    # Independent domains required before anything is published.
    "min_independent_domains": 2,
    # Severities for which a named company needs three sources and a tier 1.
    "grave_severities": ["serious_injury", "fatality"],
    "grave_min_sources": 3,
    "grave_requires_tier1": True,
}


@dataclass
class Config:
    """A mapping of thresholds with DEFAULTS behind it."""

    values: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.values.get(key, DEFAULTS.get(key))

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, DEFAULTS.get(key, default))


def default_config() -> Config:
    return Config(dict(DEFAULTS))
