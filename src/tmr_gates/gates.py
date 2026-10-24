"""Publication gates: deterministic rules that decide whether a verified
incident may be published, and what must be stripped from its public text.

There is deliberately no model here. A model answers "do these sources describe
the same event"; the gates answer "may this be published", and every rule in
them can be read, tested and reproduced: two independent domains, source tiers,
no future dates, three sources and a tier 1 outlet for a death or serious
injury attributed to a named company, blocking flags from the adversarial
pass, a risk ceiling, a separate policy for court records, and a stripper for
the names of private individuals.

The comments record why each rule exists, usually a case in the register that
went wrong without it. The README documents the rules themselves.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, timedelta
from difflib import SequenceMatcher

from .config import Config
from .tiers import tier_of


@dataclass
class Decision:
    publish: bool
    reasons: list[str] = field(default_factory=list)
    checks: dict = field(default_factory=dict)

    def fail(self, reason: str) -> "Decision":
        self.publish = False
        self.reasons.append(reason)
        return self


def independent_domains(sources: list[dict]) -> list[str]:
    """Domains left after syndication has been collapsed.

    The same text republished by three sites of one holding is one source, not
    three. Caught by similarity of the article body: reprints almost never
    rewrite the text.
    """
    kept: list[tuple[str, str]] = []
    for s in sources:
        domain = (s.get("domain") or "").lower().removeprefix("www.")
        if not domain:
            continue
        # Tier 3 does not count as independent corroboration. Otherwise "two
        # independent papers" could be one real one plus a reddit thread, and
        # the gates would pass an allegation propped up by a social media post.
        if tier_of(domain) > 2:
            continue
        body = re.sub(r"\W+", " ", (s.get("article_text") or "")[:2500]).strip().lower()
        duplicate = False
        for kept_domain, kept_body in kept:
            if kept_domain == domain:
                duplicate = True
                break
            if body and kept_body and SequenceMatcher(None, body, kept_body).ratio() > 0.82:
                duplicate = True
                break
        if not duplicate:
            kept.append((domain, body))
    return [d for d, _ in kept]


# Disagreements that are not really disagreements.
#
# The gates used to disqualify a case for ANY item in the `disagreements` list,
# and the model, asked to "list the disagreements", dutifully listed everything:
# a source's silence, a difference in retelling, the publication dates of the
# articles, rounding of the time. That accumulated 59 cases with a public
# Disputed mark, and the share crossed the threshold at which the pipeline
# switches its own publishing off.
#
# Materiality is now judged by the model itself (`material` in the verification
# rules): it sees the texts, the regular expression sees only a retelling. The
# expression remains a safeguard with two purposes: it judges old records made
# before the field existed, and it drops items where the model set
# material=true but itself described the disagreement as silence or a trifle.
# It only removes, never adds.
_NOT_A_CONTRADICTION = re.compile(
    r"(?i)("
    # silence: only two statements can contradict each other
    r"do(?:es)? not (?:specify|mention|name|state|identify|give|provide|report|confirm)"
    r"|not (?:specified|mentioned|named|stated|identified|given|provided|reported)"
    r"|no (?:source )?(?:mention|specifies|provides|gives|states|confirms)"
    r"|without (?:naming|specifying|mentioning)|omits?\b|silent (?:on|about)"
    r"|only .{0,30}(?:mentions|identifies|specifies)"
    r"|lacks? (?:the |a )?(?:detail|specific|mention)"
    # the publication date of an article is not the date of the event
    r"|publication date|date the article|article'?s? date|when the article"
    r"|published \d|dateline"
    # the model itself called the disagreement minor or possibly imaginary
    r"|minor (?:discrepancy|difference|timing)|slight(?:ly|)? (?:differ|discrepan)"
    r"|may refer to the same|adjacent (?:cities|towns)"
    r"|more generally|a turn of phrase|wording"
    r")"
)


def material_disagreements(disagreements: list) -> list[str]:
    """Keep only the disagreements that are a contradiction between two sources about a fact.

    Accepts both forms: dicts with a `material` field from the current model,
    and bare strings from old records, which are judged by the expression alone.
    """
    kept = []
    for d in disagreements or []:
        if isinstance(d, dict):
            # The model's decision is final and the expression is not applied to it.
            #
            # The expression used to run over `detail` too, "as a safeguard". But
            # `detail` is an explanation, and the prompt explicitly asks why this
            # is or is not a contradiction. So the phrase "This is a
            # contradiction, not merely a difference in wording" contained the
            # word "wording" and cancelled a disagreement about different makers;
            # "S3 does not mention the injury count" cancelled a disagreement
            # about the number of dead. A safeguard that reads the explanation
            # cancels exactly what is being explained.
            if d.get("material"):
                kept.append(str(d.get("detail") or d.get("fact") or "unspecified disagreement"))
            continue

        # Old records are bare strings without a model decision. Only those are
        # judged by the expression.
        text = str(d).strip()
        if not text or _NOT_A_CONTRADICTION.search(text):
            continue
        kept.append(text)
    return kept


# The vocabulary of events the register keeps. The list is closed on purpose: a
# register of incidents knows what an incident is, and whatever does not fit
# does not become one because three outlets wrote about it.
#
# The occasion: 3 of the 4 most recent publications turned out not to be
# incidents, Unitree's stock market debut, a Serve partnership with Grubhub, an
# Uber partnership with Lucid and Nuro. The register is sorted by date, so this
# is what the first visitor saw. The adversarial pass has a `no_incident` flag
# for this and never once raised it: risk_score 0.10 to 0.15, empty red_flags.
# The model's judgement is unreliable here; a list of types is not.
INCIDENT_TYPES = {
    "collision", "crash", "malfunction", "injury", "fatality", "death", "fire",
    "near_miss", "entrapment", "runaway", "property_damage",
    # Events without a victim but with an act of a regulator or a court are
    # material for the register too: they show how an incident ended.
    "recall", "investigation", "lawsuit", "settlement", "fine", "citation",
}

# Severities at which something really happened. Past these the type is not asked.
HARM_SEVERITIES = {"minor_injury", "serious_injury", "fatality", "property_damage"}

# An event without a victim is still an event: a collision in which nobody was
# touched remains a collision. So for `no_harm` it is enough that the type is
# recognised from the vocabulary. The exception is the types that themselves
# assert harm: "injury" with `no_harm` is not an event but a contradiction in
# the account's own testimony.
NO_HARM_KEEPS = INCIDENT_TYPES - {"injury", "fatality", "death"}


def incident_type_key(incident_type: str | None) -> str:
    """Reduce an event type to one word of the vocabulary, or empty if it does not reduce."""
    text = (incident_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in INCIDENT_TYPES:
        return text
    # A negation before the type cancels the type. Splitting on "_" turned
    # "non_collision" into a separate token "collision", so a collision that did
    # not happen counted as a collision, exactly what this comment promised to
    # guard against.
    if re.search(r"(?i)\b(non|no|not|without|denied|unconfirmed|alleged)\b", text.replace("_", " ")):
        return ""
    for word in text.split("_"):
        if word in INCIDENT_TYPES:
            return word
    return ""


def check_is_incident(incident_type: str | None, severity: str | None) -> str | None:
    """The reason for refusal if this is not an incident. None if it is.

    Severity decides, not type. The model writes the type as free text, and a
    dry run over the register showed where that leads: a rule built on type
    withdrew Cruise dragging a pedestrian twenty feet ("pedestrian struck and
    dragged by autonomous vehicle" is not in the vocabulary) and a recall of
    a hundred and five Zoox robotaxis. If a person was hurt or property was
    damaged, it is an incident whatever it was called.

    Asking the type only makes sense where nothing happened: that is exactly
    where the stock market debut and the partnerships ended up.
    """
    sev = (severity or "").lower()
    if sev in HARM_SEVERITIES:
        return None
    if sev != "no_harm":
        return "severity could not be established, so there is nothing to say happened"

    key = incident_type_key(incident_type)
    if key not in NO_HARM_KEEPS:
        return (
            "nobody was hurt, nothing was damaged and no regulator or court acted: "
            f"'{incident_type or 'unknown'}'"
        )
    return None



def court_document(sources: list[dict]) -> bool:
    """Whether the sources include a court document with its own text.

    A complaint or a court decision is a public record, not someone's account
    of it, so two independent outlets are not needed on top: the register
    promises "an act of a regulator or a court" as an event. But only with the
    text: a bare row in a court index (name, number, date) does not yet say
    what happened."""
    for s in sources:
        domain = (s.get("domain") or "").lower().removeprefix("www.")
        if domain == "courtlistener.com" and len(s.get("article_text") or "") >= 1500:
            return True
    return False


# Adversarial flags that do not block a case built on a court document.
COURT_NON_BLOCKING = {"named_private_individual", "unattributed_accusation", "stale_as_new"}


def min_score(cfg: Config, sources: list[dict]) -> float:
    """The verification threshold, lower for a case built on a court document.

    The model rates its confidence by how well the sources agree with each
    other; a single document with no second source honestly gets about 0.8
    (Velez v. Tesla: 0.82 with date, severity and company), and the general
    threshold of 0.85 would cut off every such lawsuit. The document is a
    primary record in itself, so court_min_verification_score applies to it.
    """
    base = float(cfg["min_verification_score"])
    if court_document(sources):
        return min(base, float(cfg.get("court_min_verification_score") or 0.75))
    return base


def required_domains(cfg: Config, sources: list[dict]) -> int:
    return 1 if court_document(sources) else int(cfg["min_independent_domains"])


def precheck_sources(*, cfg: Config, sources: list[dict]) -> Decision:
    """The conditions that do not depend on the model at all.

    These are exactly checks 2 and 3 of `evaluate`, pulled forward. Sources from
    one domain, or tier 3 alone, fail the gates whatever the model says, so
    paying for two model passes over such material makes no sense. The strict
    subset relation to `evaluate` matters more than the saving here: this
    function may only sift out what would have been sifted out anyway, and
    never allow anything.
    """
    decision = Decision(publish=True)
    domains = independent_domains(sources)
    decision.checks["independent_domains"] = domains
    need = required_domains(cfg, sources)
    if len(domains) < need:
        decision.fail(f"only {len(domains)} independent domain(s), need {need}")
    tiers = sorted(tier_of(d) for d in domains)
    decision.checks["tiers"] = tiers
    if not tiers or min(tiers) > 2:
        decision.fail("no tier1 or tier2 source among independent domains")
    return decision


# The subject of the register is commercial physical robots and autonomous
# machines. A find can pass every other gate without being about them: on
# 2026-10-03 the fast lane published a lawsuit by the family of a person shot by
# an ICE agent, because two independent papers, a date, an outcome and the type
# "lawsuit" were all in place. The model answers a question about the event, not
# about whether there is a robot in it; this is checked in code.
_ROBOT_SUBJECT = re.compile(
    r"(?i)\b(robot\w*|cobot\w*|humanoid\w*|robotaxi\w*|autonomous|self-driving|"
    r"driverless|automated (?:guided|vehicle|machine|system|forklift)|\bagv\b|"
    r"exoskeleton\w*|palletis\w*|palletiz\w*|surgical system|da vinci|roomba|"
    r"robo-?vac\w*|lawn ?mower|delivery (?:bot|vehicle|pod)|drone\w*|unmanned|"
    r"waymo|zoox|cruise|optimus|unitree|starship|nuro|serve robotics|coco|kiwibot|"
    r"boston dynamics|figure ai|agility|digit)\b"
)
_ROBOT_CATEGORIES = {
    "autonomous_vehicle", "delivery", "humanoid", "robot_arm", "cobot", "industrial",
    "warehouse_amr", "surgical", "consumer", "service", "agricultural",
}


def check_robot_subject(verification: dict) -> str | None:
    """None if the account of the event contains a commercial robot or an autonomous machine."""
    if verification.get("category") in _ROBOT_CATEGORIES and verification.get("robot_model"):
        return None
    text = " ".join(
        str(verification.get(k) or "")
        for k in ("title", "summary", "robot_model", "environment", "company")
    )
    if _ROBOT_SUBJECT.search(text):
        return None
    return "no commercial robot or automated machine in the account of the event"


def precheck_verification(
    *,
    cfg: Config,
    verification: dict,
    date_of_incident: str | None,
    date_precision: str | None,
    sources: list[dict],
    today: date | None = None,
) -> Decision:
    """The rules that the first model pass alone can settle, before the
    adversarial pass is paid for.

    Same subset principle as precheck_sources: rules 1, 4a, 5, 6 (score only)
    and 8. If they already fail, the adversarial review cannot rescue the case
    and would cost a second model call per item. Its independence is intact:
    it still never sees the first pass's conclusions, it simply does not run
    on what is already disqualified.
    """
    today = today or date.today()
    decision = Decision(publish=True)

    if not verification.get("same_event"):
        decision.fail("sources do not describe the same event")

    not_incident = check_is_incident(
        verification.get("incident_type"), verification.get("severity")
    )
    decision.checks["incident_type"] = verification.get("incident_type")
    if not_incident:
        decision.fail(not_incident)

    no_robot = check_robot_subject(verification)
    decision.checks["robot_subject"] = no_robot is None
    if no_robot:
        decision.fail(no_robot)

    disagreements = material_disagreements(verification.get("disagreements"))
    decision.checks["disagreements"] = disagreements
    if disagreements:
        decision.fail(f"sources disagree on key facts: {'; '.join(disagreements)[:200]}")

    score = float(verification.get("verification_score") or 0)
    decision.checks["verification_score"] = score
    threshold = min_score(cfg, sources)
    if score < threshold:
        decision.fail(f"verification score {score:.2f} below {threshold}")

    decision.checks["date_precision"] = date_precision
    if not date_of_incident or date_precision not in ("day", "month"):
        decision.fail(f"date of incident is {date_precision or 'missing'}, need day or month")

    parsed = _parse_date(date_of_incident)
    if parsed:
        if parsed > today + timedelta(days=1):
            decision.fail(f"date of incident {parsed} is in the future")
        published = [_parse_date(s.get("published_at")) for s in sources]
        earliest = min((p for p in published if p), default=None)
        if earliest and parsed > earliest + timedelta(days=2):
            decision.fail(
                f"date of incident {parsed} is later than the earliest source {earliest}"
            )
    return decision


def evaluate(
    *,
    cfg: Config,
    sources: list[dict],
    verification: dict | None,
    adversarial: dict | None,
    company: str | None,
    severity: str | None,
    incident_type: str | None = None,
    date_of_incident: str | None,
    date_precision: str | None = "day",
    today: date | None = None,
) -> Decision:
    """Every publication rule at once. None outweighs another: a failure of
    any single rule means the case waits, there is no weighted sum.

    `sources` are dicts with url, domain, tier, published_at and article_text;
    `verification` is the model's cross-verification; `adversarial` is the
    adversarial pass with risk_score and blocking flags. The returned Decision
    carries the verdict, every failed rule and what each rule saw.
    """
    today = today or date.today()
    decision = Decision(publish=True)

    if not cfg["auto_publish"]:
        return decision.fail("auto_publish is off (circuit breaker or manual switch)")

    if not verification:
        return decision.fail("cross verification did not complete")
    if not adversarial:
        return decision.fail("adversarial review did not complete")

    # 1. The same event
    if not verification.get("same_event"):
        decision.fail("sources do not describe the same event")

    # 2. Independent domains (a court document with text is enough on its own)
    domains = independent_domains(sources)
    decision.checks["independent_domains"] = domains
    need = required_domains(cfg, sources)
    decision.checks["court_document"] = need == 1
    if len(domains) < need:
        decision.fail(f"only {len(domains)} independent domain(s), need {need}")

    # 3. Source tiers: tier 3 is never enough on its own
    tiers = sorted(tier_of(d) for d in domains)
    decision.checks["tiers"] = tiers
    if not tiers or min(tiers) > 2:
        decision.fail("no tier1 or tier2 source among independent domains")

    # Policy for court documents (editorial decision of 2026-10-22): a complaint
    # or a court decision is the primary record of an allegation. The title says
    # "Lawsuit alleges", the names of private individuals are removed by the
    # stripper, so the grave rule, the flags about named individuals,
    # unattributed accusation and "old as new" (a 2026 lawsuit about a 2023
    # event, with the event date on the card) do not block, and risk is allowed
    # up to court_max_risk_score.
    court = court_document(sources)

    # 4. The stronger rule for accusations
    grave = severity in set(cfg["grave_severities"])
    decision.checks["grave"] = grave
    if grave and company and court:
        decision.checks["grave_waived"] = "court_document"
    elif grave and company:
        if len(domains) < int(cfg["grave_min_sources"]):
            decision.fail(
                f"named company with {severity}: needs {cfg['grave_min_sources']} sources"
            )
        if cfg["grave_requires_tier1"] and (not tiers or tiers[0] != 1):
            decision.fail(f"named company with {severity}: needs at least one tier1 source")

    # 4b. Is this an incident at all
    not_incident = check_is_incident(incident_type, severity)
    decision.checks["incident_type"] = incident_type
    if not_incident:
        decision.fail(not_incident)

    # 5. Contradictions in key facts
    disagreements = material_disagreements(verification.get("disagreements"))
    decision.checks["disagreements"] = disagreements
    if disagreements:
        decision.fail(f"sources disagree on key facts: {'; '.join(disagreements)[:200]}")

    # 6. Thresholds
    score = float(verification.get("verification_score") or 0)
    risk = float(adversarial.get("risk_score") or 0)
    decision.checks["verification_score"] = score
    decision.checks["risk_score"] = risk
    threshold = min_score(cfg, sources)
    if score < threshold:
        decision.fail(f"verification score {score:.2f} below {threshold}")
    risk_cap = float(cfg.get("court_max_risk_score") or 0.75) if court else float(cfg["max_risk_score"])
    if risk > risk_cap:
        decision.fail(f"risk score {risk:.2f} above {risk_cap}")

    # 7. Blocking flags of the adversarial pass
    blocking = adversarial.get("blocking") or []
    decision.checks["blocking_flags"] = [f.get("flag") for f in blocking]
    waived = []
    for flag in blocking:
        name = flag.get("flag")
        if court and name in COURT_NON_BLOCKING:
            waived.append(name)
            continue
        decision.fail(f"adversarial block: {name}")
    if waived:
        decision.checks["flags_waived"] = waived

    # 8. Sanity checks on dates
    #
    # The register is chronological: the main chart is built by the year of the
    # event, and a case that cannot be placed in time simply disappears from it
    # while still being counted in the total. So the date is required, but to
    # the month: "in July" is more common in the news than an exact day, and
    # rejecting such cases would lose real incidents for the sake of tidiness.
    # A bare year without a month is too little: it stretches the event over
    # twelve months.
    decision.checks["date_precision"] = date_precision
    if not date_of_incident or date_precision not in ("day", "month"):
        decision.fail(
            f"date of incident is {date_precision or 'missing'}, need day or month"
        )

    parsed = _parse_date(date_of_incident)
    if parsed:
        if parsed > today + timedelta(days=1):
            decision.fail(f"date of incident {parsed} is in the future")
        published = [_parse_date(s.get("published_at")) for s in sources]
        earliest = min((p for p in published if p), default=None)
        if earliest and parsed > earliest + timedelta(days=2):
            decision.fail(
                f"date of incident {parsed} is later than the earliest source {earliest}"
            )

    return decision


def _parse_date(value) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


# The names of private individuals are cut out by code, not only by the prompt:
# a prompt can be talked around by phrasing, a regular expression cannot.
_TITLE_PREFIX = r"(?:Mr|Mrs|Ms|Dr|Prof|Officer|Judge|Sheriff|Sen|Rep|Gov)\.?\s+"
# Two or three capitalised words. Three, because "Regina Allen Elsea" under the
# two-word pattern became "a person Elsea", leaving the surname on the page. A
# middle initial counts as a word too.
# A name word: capitalised, possibly with a capital inside (McGee, DeSantis,
# MacArthur) or an apostrophe (O'Brien). "George McGee" used to match as
# "George Mc", and the page showed "a personGee" (TMR-0891, 2026-10-22).
_NAME_TOKEN = r"[A-Z][a-z]{1,15}(?:(?:'|)[A-Z][a-z]{1,15})?"
_NAME = rf"{_NAME_TOKEN}(?:\s+(?:[A-Z]\.|{_NAME_TOKEN}))(?:\s+[A-Z][a-z]{{2,20}}(?:[A-Z][a-z]{{1,15}})?)?"

# An age next to a name is the strongest sign of a private individual in this
# corpus: "Regina Allen Elsea, 20, was killed", "Christopher C. Pardue, 71,
# died". This also catches what the general pattern does not see: a single word
# ("Ramanjaneyulu") and non-Latin spellings.
_NAME_WITH_AGE = re.compile(
    r"\b([^\W\d_][\w'\-]{1,20}(?:\s+(?:[A-Z]\.|[^\W\d_][\w'\-]{1,20})){0,2})"
    r"(?=,\s*\d{1,3}\s*,)"
)

# "a 22-year-old trainee engineer Ramanjaneyulu was killed": the age comes
# before the name, so the general pattern does not see it, and a capitalised
# word after an age construction is almost always the victim.
# The case-insensitive flag is limited to the group on purpose: (?i) over the
# whole pattern made [A-Z] case-blind, and the first pass removed the word "was".
_NAME_AFTER_AGE = re.compile(
    r"(?i:\d{1,3}[- ]year[- ]old\s+(?:[a-z]+\s+){0,3})([A-Z][\w'\-]{2,24})"
)
_PUBLIC_ROLE = re.compile(
    r"(?i)\b(spokesperson|spokesman|spokeswoman|chief executive|ceo|cto|coo|president|"
    r"director|minister|senator|governor|mayor|attorney general|commissioner|judge|"
    r"inspector|prosecutor|official)\b"
)


# Legal forms: whatever stands next to them is an organisation, not a person.
_CORPORATE = re.compile(
    r"(?i)\b(inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|gmbh|ag|s\.?a|"
    r"b\.?v|plc|oy|ab|kk|pte|pty|holdings|group|technologies|robotics|systems|labs|"
    r"motors|automation|industries|university|college|hospital|institute|department|"
    r"administration|agency|commission|police|county|city|state|llp|firm|attorneys?|"
    r"counsel|associates|partners)\b"
)
# Words next to which Title Case means a person rather than a machine or an
# institution. Without this condition the pattern removed "Zeekr Rt", "Shanghai
# Stock Exchange", "On June" and turned a title into "a Zoox autonomous vehicle
# a person was involved". The promise is kept not by the pattern's greed but by
# the fact that all the strong signs of a person (an age next to the name, a
# form of address) are handled separately and need no context.
_PERSON_CONTEXT = re.compile(
    # Prefixes are taken with \w*, not within a word boundary: \binjur\b did not
    # match "injured", and the rule silently failed on the most common wording
    # in this corpus.
    r"(?i)\b(?:killed|kills|died|dies|dead|death|fatally|fatality|injur\w*|hurt|"
    r"wounded|hospitalis\w*|hospitaliz\w*|victim\w*|worker\w*|employee\w*|"
    r"technician\w*|engineer\w*|pedestrian\w*|cyclist\w*|patient\w*|passenger\w*|"
    r"toddler|child|children|woman|women|man|men|widow\w*|famil\w*|survived|"
    r"suffer\w*|crush\w*|struck|strikes|drag\w*|pinn\w*|trapp\w*|amputat\w*|"
    r"burn\w*|sued|suing|plaintiff\w*|defendant\w*|estate of|father|mother|son|daughter|"
    r"husband|wife|his |her |"
    # Court and medical texts (lawsuits, 2026-10-22): a doctor and a patient are
    # named next to an operation, not next to an "injury": "Dr. X used a robot
    # to operate on Y".
    r"surgeon\w*|surgery|operat\w*|doctor\w*|physician\w*|deficit\w*|diagnos\w*|"
    r"treat\w*|underwent|driving|drove|veteran\w*)"
)

# Title Case that in this corpus is almost never a person.
_NOT_A_PERSON = re.compile(
    # Makes and models of vehicles get their own list: in NHTSA titles they stand
    # in brackets ("(Hyundai Ioniq 5)") next to words about the injured, so the
    # context condition does not save them.
    r"(?i)\b(hyundai|toyota|jaguar|chrysler|ford|honda|zeekr|lucid|kia|nissan|"
    r"chevrolet|tesla|bmw|mercedes|volkswagen|volvo|ioniq|highlander|pacifica|"
    r"i-pace|palletizer|forklift|conveyor|crane|"
    # Street suffixes: the second word gives away an address more reliably than any list.
    r"drive|avenue|road|street|boulevard|lane|highway|freeway|parkway|square|"
    r"park|plaza|bridge|tunnel|airport|gigafactory|campus|mall|hollywood|gardens|"
    # Compass points begin place names, and numerals begin lists of machines.
    r"west|east|north|south|three|two|four|five|six|seven|eight|nine|ten|"
    # Countries appear in every other title and are not people.
    r"china|usa|japan|korea|germany|france|india|canada|mexico|brazil|australia|"
    r"britain|spain|italy|poland|sweden|norway|finland|israel|singapore|"
    r"vehicle\w*|robot\w*|truck\w*|car|cars|van|vans|drone\w*|exchange|stock|"
    r"market|street|"
    r"avenue|road|boulevard|county|court|university|college|airport|station|plant|"
    r"factory|warehouse|hospital|centre|center|january|february|march|april|may|june|"
    r"july|august|september|october|november|december|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|sunday|request|report|order|act|law|model|series|"
    r"driver\w*|gravity|games|olympics|cup|award|division|district|department\w*|"
    r"surgical|autonomous|arm|arms|press|machine|health|river|lake|creek|hills|"
    r"heights|valley|oaks|system|systems|pizza|cafe|restaurant|grill|store|shop)\b"
)

_FIRM_BEFORE = re.compile(r"(?i)\b(law firm|firm|counsel|attorneys?|represented by)\s+\S*\s*$")
_PLACE_PREP = re.compile(r"(?i)\b(in|at|near|outside|inside|from|across|along)\s+(?:the\s+)?$")
_MONTH_OR_DAY = re.compile(
    r"(?i)^(january|february|march|april|may|june|july|august|september|october|"
    r"november|december|monday|tuesday|wednesday|thursday|friday|saturday|sunday)$")
# A word right after the match that makes it the name of a place or a law
# rather than a person: "Rosa L. Jones Drive", "Ralph H. Johnson VAMC",
# "Federal Tort Claims Act".
_FACILITY_AFTER = re.compile(
    r"^\s+(?:Drive|Road|Street|Avenue|Boulevard|Lane|Highway|Way|Court|VAMC|VA\b|"
    r"Medical|Hospital|Center|Centre|Clinic|Act|Claims|System|Plaza|Park|Bridge|"
    r"Building|County|University|School|Airport|Station|Plant|Facility|Foundation|"
    r"Institute|Memorial|Surgical|Robotics|Technologies|Industries)\b")

# "... in San Francisco, CA": a two-letter state code after a comma means a place.
_STATE_CODE = re.compile(r"^\s*,\s*[A-Z]{2}\b")
# Place names that come up daily in this subject area and have no legal form
# next to them. The list is short on purpose: it supplements the rules, it does
# not replace them.
_KNOWN_PLACES = {
    "san francisco", "los angeles", "new york", "san jose", "santa monica",
    "san diego", "las vegas", "san antonio", "fort worth", "salt lake city",
    "new jersey", "new mexico", "north carolina", "south carolina", "west virginia",
    "new hampshire", "rhode island", "hong kong", "south korea", "new zealand",
    "great britain", "united kingdom", "united states", "el paso", "santa clara",
    "palo alto", "mountain view", "menlo park", "silicon valley",
}


def strip_private_names(
    text: str | None, *, protected: set[str] | None = None
) -> tuple[str | None, list[str]]:
    """Remove personal names that are not accompanied by a public role.

    The caution is deliberate: better to drop a spokesperson's name than to
    keep a victim's. The reason is not reputation but that an injury next to
    a name is medical data about an identifiable person, and the register
    publishes without an editor.

    The pattern itself is any two capitalised words, which also matches
    "Boston Dynamics" and "San Francisco", so before removing a match four
    signs that it is not a person are checked: the match is in `protected`
    (the register passes its company names), a corporate suffix or industry
    word stands next to it (Inc, LLC, Robotics), a comma and a state code
    follow (a place), or the match is in a short list of known places.
    Months, days, facilities named after people, roads and acts are kept.

    Do not feed regulator documents through this: they are anonymised at the
    source, and the Title Case of their headings turns the pattern into a
    shredder. Returns the cleaned text and the list of removed names.
    """
    if not text:
        return text, []

    protected_lower = {p.lower() for p in (protected or set())}
    protected_firsts = {p.split()[0] for p in protected_lower if p.split() and len(p.split()[0]) > 3}
    removed: list[str] = []

    def _not_a_person(name: str) -> bool:
        """A function word inside the match: "Tesla Model", "Vinci Surgical
        System". A month in the middle does not count: "Dawn May Bunch" is a
        person even though May is a month."""
        toks = unarticled(name).split()
        for i, tok in enumerate(toks):
            if 0 < i < len(toks) - 1 and _MONTH_OR_DAY.match(tok):
                continue
            if _NOT_A_PERSON.search(tok):
                return True
        return False

    # A Title Case heading ("Employee Is Pinned Against Heated Mold By Robotic
    # Arm") is capitalised throughout, and the general pattern turns it into
    # "a person a person a person". Such lines are judged only by the strong
    # signs: an age next to the name and a form of address. This is what the
    # warning above about primary regulator documents is about.
    words = [w for w in re.findall(r"[A-Za-z][\w'\-]*", text) if len(w) > 2]
    # 0.8, not 0.6: the complaint sentence "Dr. X used a Globus Excelsius GPS
    # robot on Y at Merit Health River Oaks in Mississippi" is 61% capitalised
    # and passed as a Title Case heading, that is, without the general pass.
    title_case = len(words) >= 4 and sum(w[0].isupper() for w in words) / len(words) > 0.8

    def unarticled(name: str) -> str:
        """"The Waymo" is the same Waymo, not a person surnamed Waymo."""
        return re.sub(r"(?i)^(the|a|an)\s+", "", name).strip()

    def replace(match: re.Match) -> str:
        name = match.group(0)
        # Context is taken from the string this replacement runs over
        # (match.string), not from the original text: after the first pass the
        # offsets differ, and "at Merit Health" was being checked at the wrong place.
        low = unarticled(name).lower()
        if low in protected_lower or low in _KNOWN_PLACES:
            return name
        if any(low.startswith(kp + " ") for kp in _KNOWN_PLACES):
            return name  # "San Francisco Bay", "New York City"
        # A company name inside the match protects it too: "Baidu Apollo" and
        # "Three Waymo" are the same company with a stray word next to it.
        if any(pn in low for pn in protected_lower if len(pn) > 3):
            return name
        # The first word of a company name protects as well: "Globus Excelsius"
        # next to "surgery" would otherwise become "a person", because the
        # register's company is "Globus Medical".
        if any(tok in protected_firsts for tok in low.split()):
            return name
        window = match.string[max(0, match.start() - 90) : match.end() + 90]
        if _PUBLIC_ROLE.search(window):
            return name
        if _not_a_person(name):
            return name
        # Title Case alone proves nothing. A name is removed only when the text
        # next to it says something happened to a person.
        if not _PERSON_CONTEXT.search(window):
            return name
        # The legal form is looked for right next to the match, not in a wide
        # window: "Amazon" thirty characters from a worker's name does not make
        # that name a company. To the right, right next to it. To the left, only
        # a narrow list of words about a firm: a wide list gave "Nimble Robotics
        # injured John Carter", where the company name two words away protected
        # the person.
        # A middle initial ("Maxwell D. Nalder") is almost certainly a person:
        # "Health" a few words to the right ("at Merit Health") does not cancel that.
        has_initial = re.search(r"\s[A-Z]\.\s", name) is not None
        if not has_initial and _CORPORATE.search(match.string[match.start() : match.end() + 24]):
            return name
        if _FIRM_BEFORE.search(match.string[max(0, match.start() - 20) : match.start()]):
            return name
        # "in East Hollywood", "at Berkman Drive", "near Austin Gigafactory": a
        # preposition of place before Title Case means an address, not a victim.
        if _PLACE_PREP.search(match.string[: match.start()]):
            return name
        if _STATE_CODE.match(match.string[match.end() :]):
            return name
        if _FACILITY_AFTER.match(match.string[match.end() :]):
            return name
        removed.append(name)
        return "a person"

    def replace_group(match: re.Match) -> str:
        """The same decision, but only the first group is removed, not the whole match."""
        name = match.group(1)
        low = unarticled(name).lower()
        # The general pattern may already have fired here: without this,
        # "a person, 20," became "a a person, 20,".
        if "a person" in low or low in {"a", "an", "the", "person"}:
            return match.group(0)
        if low in protected_lower or low in _KNOWN_PLACES:
            return match.group(0)
        if _PUBLIC_ROLE.search(match.group(0)):
            return match.group(0)
        if _CORPORATE.search(name) or _not_a_person(name):
            return match.group(0)
        removed.append(name)
        return match.group(0).replace(name, "a person", 1)

    # The age constructions go FIRST, over the original text. In the reverse
    # order the general pattern had already left "a person", and the age pattern
    # saw the word "person" in it as a surname: the result was "a a person, 20,".
    cleaned = _NAME_WITH_AGE.sub(replace_group, text)
    cleaned = _NAME_AFTER_AGE.sub(replace_group, cleaned)
    cleaned = re.sub(_TITLE_PREFIX + _NAME, replace, cleaned)
    if not title_case:
        cleaned = re.sub(_NAME, replace, cleaned)
    return cleaned, removed
