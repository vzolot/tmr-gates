# tmr-gates

The publication gates of [The Machine Record](https://themachinerecord.com), an open register of safety incidents involving commercial robots, as a standalone Python package with no dependencies.

The register publishes without human pre-moderation. A language model answers one question, "do these sources describe the same real-world event, and how well", and an adversarial pass looks for defamation, satire, unattributed accusations and stale news. Everything after that is rules. This package is those rules: they decide whether a verified event may be published, what evidence a grave allegation needs, which sources count, and which names must never appear in public text. Every rule is deterministic, documented here and covered by tests, so anyone can run the register's own cases through the same gates and get the same decisions.

The code is extracted unchanged from the production pipeline. The inline comments record why each rule exists, usually a case in the register that went wrong without it; this README documents the rules themselves.

## Install

```
pip install tmr-gates
```

or straight from the repository:

```
pip install git+https://github.com/vzolot/tmr-gates@v0.1.1
```

Python 3.9 or newer. No runtime dependencies.

## Use

```python
from datetime import date
from tmr_gates import default_config, evaluate, precheck_sources, strip_private_names

cfg = default_config()

sources = [
    {"url": "https://www.reuters.com/...", "domain": "reuters.com", "tier": 1,
     "published_at": "2026-05-02", "article_text": "..."},
    {"url": "https://www.localpaper.com/...", "domain": "localpaper.com", "tier": 2,
     "published_at": "2026-05-03", "article_text": "..."},
]

# Cheap checks before paying for a model call: enough independent domains, not all tier 3.
pre = precheck_sources(cfg=cfg, sources=sources)
assert pre.publish, pre.reasons

verification = {          # the model's cross-verification of the sources
    "same_event": True,
    "verification_score": 0.91,
    "incident_type": "injury",
    "disagreements": [],
}
adversarial = {"risk_score": 0.1, "blocking": []}   # the adversarial pass

decision = evaluate(
    cfg=cfg, sources=sources, verification=verification, adversarial=adversarial,
    company="Robot Co.", severity="minor_injury",
    date_of_incident="2026-05-01", date_precision="day", today=date(2026, 5, 4),
)
print(decision.publish, decision.reasons, decision.checks)

# Public text never carries the names of private individuals.
clean = strip_private_names("Worker John Smith, 34, was pinned by the arm.")
```

`Decision.publish` is the verdict, `Decision.reasons` lists every failed rule, and `Decision.checks` records what each rule saw, so a refusal can be audited without rerunning anything.

## The rules

`evaluate()` applies them in this order. Each failure is recorded; the decision fails if any rule fails.

| # | Rule | Config key, default |
|---|------|---------------------|
| 0 | Kill switch. When auto-publishing is off nothing passes. The register's circuit breaker flips this when the share of disputed cases rises. | `auto_publish`, true |
| 1 | The sources describe the same event, according to the model's cross-verification. | |
| 2 | Enough independent domains. Syndication copies, subdomains and link shorteners of one outlet count once. A court record with full text is a primary document and suffices alone. | `min_independent_domains`, 2 |
| 3 | At least one tier 1 or tier 2 source among the independent domains. Tier 3 (social networks, blogs, tabloids, aggregators) is never enough on its own and is not counted as corroboration. | |
| 4 | A death or serious injury attributed to a named company needs three independent sources, one of them tier 1. A court record waives this: the allegation is the filing itself, on the record. | `grave_severities`, `grave_min_sources` 3, `grave_requires_tier1` true |
| 4a | The event is an incident at all, not a product launch, a demo or an opinion piece; a commercial robot or automated machine is the subject. | |
| 5 | No material disagreement between sources on company, model, date, place, severity or what happened. Silence is not a contradiction; a wording difference that is explained is not a contradiction. | |
| 6 | Verification score at or above the threshold, risk score at or below the ceiling. Court records get a lower score bar and a higher risk ceiling; press in a language other than English gets a ceiling between the two. | `min_verification_score` 0.80, `max_risk_score` 0.35, `court_min_verification_score` 0.75, `court_max_risk_score` 0.75, `foreign_max_risk_score` 0.5 |
| 7 | No blocking flag from the adversarial pass: satire or fake, defamation pattern, single source behind many wrappers, named private individual, unattributed accusation, stale event presented as new. For court records the last three are waived and recorded, because a complaint is by nature an attributed accusation about named people on a past date. For press in another language the named individual and stale flags are waived and recorded, because the name stripper removes the name and rule 8 still requires a correct event date. | |
| 8 | Date sanity. The date of the incident is known to the day or the month, is not in the future, and is not later than the earliest publication by more than two days. | |

`precheck_sources()` runs rules 2 and 3 before any model call, and `precheck_verification()` runs 1, 4a, 5, 6 and 8 after the first model pass, so a bundle that cannot pass is never sent to the expensive adversarial pass. Both are strict subsets of `evaluate()`: they can only reject what it would reject.

### Source tiers

`tier_of(domain)` returns 1, 2 or 3.

- Tier 1: wire agencies, national outlets and public broadcasters in the US, UK, Germany, France, Italy, Spain, the Netherlands, Poland, Switzerland, Austria, Japan, Korea, Hong Kong and Taiwan; regulators and courts through government suffixes (`.gov`, `.gouv.fr`, `.bund.de`, `.go.jp`, `.go.kr`, `.europa.eu` and others); court dockets on CourtListener.
- Tier 2: every unknown domain, on purpose. Regional papers are where most incidents first appear, and demoting the unknown would switch corroboration off. The price of that assumption is paid by rule 4, where it matters most.
- Tier 3: social networks, blogs, video platforms, tabloids, content farms and syndication portals that republish other outlets' text under their own domain.

The lists live in `tmr_gates/tiers.py` and are the register's editorial judgement, published so it can be argued with.

### Press in other languages

`evaluate(..., lang="de")` applies the policy for press in a language other than English when `lang` is set and is not `en`; the register passes the locale code its collector used, never a language detected from the text. Rules 2, 3, 4 and 8 are unchanged: two independent domains, a tier 1 or tier 2 source, three sources for a grave allegation, a correct event date. What changes is rule 6 (`foreign_max_risk_score`, 0.5) and two flags of rule 7, `named_private_individual` and `stale_as_new`, which are waived and recorded in `checks["flags_waived"]`. The reasoning: a regional paper in Gunma or Bürstadt names the injured worker and writes "yesterday", and the adversarial pass reads that as risk; the register strips the name before publication and dates the event itself, so the flags describe the source, not the case. A court record keeps its own policy whatever the language.

### Court records

`court_document(sources)` is true when a source is a docket on courtlistener.com with at least 1,500 characters of text. Such a record can carry a case alone (rule 2), waives the three-source rule for grave allegations (rule 4) and three adversarial flags (rule 7), and is judged against its own thresholds (rule 6). The reasoning: a filed complaint is a primary document, attributed by definition, and its allegations are reported as allegations.

### Private individuals

`strip_private_names(text)` removes the names of private people from public text while keeping company names, places, public officials by role, and product names. It is a regular-expression stripper with explicit lists of protected forms (facilities, roads, months, corporate suffixes, known places). Names of officials, spokespeople and company representatives are kept when their role is stated. The register also runs a defamation rewriter before this; the stripper is the last line.

## How The Machine Record uses it

The production pipeline imports this package and applies the gates to every candidate case after capture, corroboration and two model passes. Thresholds come from a database table so the circuit breaker can change them without a deploy. The methodology page at [themachinerecord.com/methodology](https://themachinerecord.com/methodology) describes the same rules in prose; this package is the executable version.

## Tests

```
pip install -e .[test]
pytest -q
```

The tests are the acceptance criteria of the register: a tabloid alone never passes, a death attributed to a named company needs three sources and a tier 1, a future date fails, a court record passes with the flags a complaint always carries, and the stripper removes a named patient but keeps a hospital named after a person.

## Licence

MIT. The case data of the register is published separately under CC BY 4.0 at [vzolot/machine-record-data](https://github.com/vzolot/machine-record-data).
