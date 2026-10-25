# Changelog

## 0.2.0 (2026-10-25)

- `evaluate()` takes `lang`, the collector's language code of the lead source. For press in a language other than English the risk ceiling is `foreign_max_risk_score` (0.5) and the flags `named_private_individual` and `stale_as_new` are waived and recorded (`FOREIGN_NON_BLOCKING`, `foreign_press()`). Every other rule is unchanged; a court record keeps the court policy whatever the language.
- Without `lang` the behaviour is exactly that of 0.1.x.
- 11 new checks in the tests (77 in all).

## 0.1.1 (2026-10-24)

- All inline comments translated into English; no change in behaviour, the tests are unchanged.
- Publishing workflow for PyPI (trusted publishing on a version tag).

## 0.1.0 (2026-10-23)

First release, extracted unchanged from the pipeline of The Machine Record.

- `evaluate()`, `precheck_sources()`, `precheck_verification()`: the publication gates.
- Source tiers for US, UK, EU, Japan, Korea, China and government domains.
- Court-record policy: a lone court document with full text can carry a case.
- `strip_private_names()`: removes names of private individuals from public text.
- Tests ported from the pipeline (66 checks).
