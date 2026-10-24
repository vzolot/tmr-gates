"""Tests of the publication gates.

These rules are the only thing standing between an automaton and a public
accusation against a named company. So they are checked by code, not by
review: "it seems to work" is not enough here.

    pytest, or: python tests/test_gates.py
"""
from __future__ import annotations

from datetime import date, timedelta

from tmr_gates.config import Config, DEFAULTS
from tmr_gates.tiers import tier_of
from tmr_gates.gates import (
    check_is_incident,
    court_document,
    evaluate,
    material_disagreements,
    independent_domains,
    precheck_sources,
    precheck_verification,
    strip_private_names,
)

CFG = Config(dict(DEFAULTS))

OK_VERIFICATION = {
    "same_event": True,
    "verification_score": 0.93,
    "disagreements": [],
    # The event type is as much a publication condition as the date or two
    # domains: a register of incidents does not publish what is not an incident.
    "incident_type": "collision",
    "severity": "minor_injury",
    # The check_robot_subject gate (2026-10-03) requires a robot in the account:
    # a lawsuit by the family of a person shot by an ICE agent passed everything
    # else and was published as TMR-0776.
    "title": "Delivery robot struck a pedestrian in Austin",
    "summary": "A Starship delivery robot collided with a pedestrian on Tuesday.",
    "category": "delivery",
    "robot_model": "Starship",
}
OK_ADVERSARIAL = {"risk_score": 0.05, "red_flags": [], "blocking": []}

TIER1 = {"url": "https://reuters.com/a", "domain": "reuters.com",
         "article_text": "A delivery robot struck a pedestrian in Austin on Tuesday. " * 20,
         "published_at": "2026-07-20"}
TIER1B = {"url": "https://bbc.com/b", "domain": "bbc.com",
          "article_text": "Officials said the machine collided with a person near the campus. " * 20,
          "published_at": "2026-07-20"}
TIER2 = {"url": "https://kxan.com/c", "domain": "kxan.com",
         "article_text": "Local police confirmed the collision outside the university. " * 20,
         "published_at": "2026-07-21"}
TIER3 = {"url": "https://reddit.com/r/x/d", "domain": "reddit.com",
         "article_text": "Saw a robot hit someone downtown today, wild stuff. " * 20,
         "published_at": "2026-07-20"}


def check(name: str, condition: bool) -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}  {name}")
    return condition


def main() -> int:
    print("\nGates for automatic publication\n")
    ok = True

    # A single tier 3 source never publishes, under any conditions
    d = evaluate(cfg=CFG, sources=[TIER3], verification=OK_VERIFICATION,
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="minor_injury", incident_type="collision",
                 date_of_incident="2026-07-20")
    ok &= check("single tier3 source never publishes", not d.publish)

    # Even several tier 3 domains are not enough
    tier3b = {**TIER3, "url": "https://x.com/e", "domain": "x.com",
              "article_text": "Different wording about a robot hitting someone. " * 20}
    d = evaluate(cfg=CFG, sources=[TIER3, tier3b], verification=OK_VERIFICATION,
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="minor_injury", incident_type="collision",
                 date_of_incident="2026-07-20")
    ok &= check("several tier3 domains still never publish", not d.publish)

    # Two tier 1 sources with a score above the threshold publish on their own
    d = evaluate(cfg=CFG, sources=[TIER1, TIER1B], verification=OK_VERIFICATION,
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="minor_injury", incident_type="collision",
                 date_of_incident="2026-07-20")
    ok &= check("two tier1 sources with score 0.93 publish", d.publish)

    # The stronger rule for accusations: grave harm requires tier 1
    d = evaluate(cfg=CFG, sources=[TIER2, {**TIER2, "url": "https://wfaa.com/f",
                 "domain": "wfaa.com", "article_text": "Another regional account entirely. " * 20}],
                 verification=OK_VERIFICATION, adversarial=OK_ADVERSARIAL,
                 company="Starship", severity="fatality", incident_type="collision", date_of_incident="2026-07-20")
    ok &= check("named company plus fatality needs a tier1 source", not d.publish)

    # Two domains are no longer enough for a fatality with a named company:
    # `grave_min_sources` used to equal the ordinary threshold, so the stronger
    # requirement strengthened nothing.
    d = evaluate(cfg=CFG, sources=[TIER1, TIER2], verification=OK_VERIFICATION,
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="fatality", incident_type="collision",
                 date_of_incident="2026-07-20")
    ok &= check("named company plus fatality needs more than two sources", not d.publish)

    d = evaluate(cfg=CFG, sources=[TIER1, TIER1B, TIER2], verification=OK_VERIFICATION,
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="fatality", incident_type="collision",
                 date_of_incident="2026-07-20")
    ok &= check("named company plus fatality with three sources publishes", d.publish)

    # Low score
    d = evaluate(cfg=CFG, sources=[TIER1, TIER1B],
                 verification={**OK_VERIFICATION, "verification_score": 0.7},
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="minor_injury", incident_type="collision",
                 date_of_incident="2026-07-20")
    ok &= check("verification score below threshold blocks", not d.publish)

    # Contradictions in key facts
    d = evaluate(cfg=CFG, sources=[TIER1, TIER1B],
                 verification={**OK_VERIFICATION, "disagreements": ["sources name different cities"]},
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="minor_injury", incident_type="collision",
                 date_of_incident="2026-07-20")
    ok &= check("disagreement on key facts blocks", not d.publish)

    # A blocking flag from the adversarial pass
    d = evaluate(cfg=CFG, sources=[TIER1, TIER1B], verification=OK_VERIFICATION,
                 adversarial={"risk_score": 0.2, "red_flags": [],
                              "blocking": [{"flag": "unattributed_accusation",
                                            "evidence": "says the firm ignored safety rules"}]},
                 company="Starship", severity="minor_injury", incident_type="collision", date_of_incident="2026-07-20")
    ok &= check("unattributed accusation is blocked by the adversarial pass", not d.publish)

    # A date in the future
    future = (date.today() + timedelta(days=10)).isoformat()
    d = evaluate(cfg=CFG, sources=[TIER1, TIER1B], verification=OK_VERIFICATION,
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="minor_injury", incident_type="collision",
                 date_of_incident=future)
    ok &= check("incident date in the future blocks", not d.publish)

    # Kill switch
    off = Config({**DEFAULTS, "auto_publish": False})
    d = evaluate(cfg=off, sources=[TIER1, TIER1B], verification=OK_VERIFICATION,
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="minor_injury", incident_type="collision",
                 date_of_incident="2026-07-20")
    ok &= check("kill switch stops everything", not d.publish)

    print("\nSyndication and independence\n")
    syndicated = {**TIER1, "url": "https://otheroutlet.com/g", "domain": "otheroutlet.com"}
    domains = independent_domains([TIER1, syndicated])
    ok &= check("same text on two domains counts as one source", len(domains) == 1)
    ok &= check("different texts count separately",
                len(independent_domains([TIER1, TIER1B])) == 2)

    print("\nSource quality\n")
    tabloid = {"url": "https://dailymail.co.uk/x", "domain": "dailymail.co.uk",
               "article_text": "A robot went berserk at the warehouse, sources say. " * 20,
               "published_at": "2026-07-20"}
    syndicated_portal = {"url": "https://autos.yahoo.com/y", "domain": "autos.yahoo.com",
                         "article_text": "Entirely different wording about the same crash. " * 20,
                         "published_at": "2026-07-20"}
    ok &= check("tabloid is tier3", tier_of("dailymail.co.uk") == 3)
    ok &= check("republishing portal is tier3", tier_of("autos.yahoo.com") == 3)
    ok &= check("rewrite farm is tier3", tier_of("futurism.com") == 3)
    ok &= check("local paper stays tier2", tier_of("statesman.com") == 2)
    ok &= check("trade press stays tier2", tier_of("therobotreport.com") == 2)
    ok &= check("agency stays tier1", tier_of("reuters.com") == 1)
    ok &= check("tier3 does not count as an independent domain",
                independent_domains([TIER1, tabloid, TIER3]) == ["reuters.com"])
    d = evaluate(cfg=CFG, sources=[TIER1, tabloid], verification=OK_VERIFICATION,
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="minor_injury", incident_type="collision",
                 date_of_incident="2026-07-20")
    ok &= check("one real outlet plus a tabloid is not two sources", not d.publish)
    d = evaluate(cfg=CFG, sources=[TIER1, syndicated_portal], verification=OK_VERIFICATION,
                 adversarial=OK_ADVERSARIAL, company="Starship", severity="minor_injury", incident_type="collision",
                 date_of_incident="2026-07-20")
    ok &= check("one real outlet plus a portal reprint is not two sources", not d.publish)

    print("\nEarly exits must never be more permissive than the gates\n")
    # Both early exits exist only so that the model is not paid for material the
    # gates will reject anyway. So the one property to prove is that a failed
    # early exit always means a failed evaluate on the same data. The converse
    # is not needed: the gates are allowed to reject more.
    syndicated_pair = [TIER1, {**TIER1, "url": "https://otheroutlet.com/h",
                               "domain": "otheroutlet.com"}]
    cases = [
        ("one independent domain", syndicated_pair, OK_VERIFICATION, "2026-07-20"),
        ("only tier3 domains", [TIER3, {**TIER3, "url": "https://x.com/i", "domain": "x.com",
          "article_text": "A completely different retelling of the same thing. " * 20}],
         OK_VERIFICATION, "2026-07-20"),
        ("not the same event", [TIER1, TIER1B],
         {**OK_VERIFICATION, "same_event": False}, "2026-07-20"),
        ("verification score below threshold", [TIER1, TIER1B],
         {**OK_VERIFICATION, "verification_score": 0.4}, "2026-07-20"),
        ("date of incident missing", [TIER1, TIER1B], OK_VERIFICATION, None),
        ("sources disagree on key facts", [TIER1, TIER1B],
         {**OK_VERIFICATION, "disagreements": ["different company"]}, "2026-07-20"),
    ]
    for name, sources, verification, incident_date in cases:
        pre = precheck_sources(cfg=CFG, sources=sources)
        early = precheck_verification(
            cfg=CFG, verification=verification, date_of_incident=incident_date,
            date_precision="day" if incident_date else None, sources=sources)
        skipped = not (pre.publish and early.publish)
        full = evaluate(cfg=CFG, sources=sources, verification=verification,
                        adversarial=OK_ADVERSARIAL, company="Starship",
                        severity="minor_injury", incident_type="collision", date_of_incident=incident_date)
        ok &= check(f"{name}: skipped early", skipped)
        ok &= check(f"{name}: gates would have refused it anyway", not full.publish)

    # And the other way round: what the gates publish, no early exit may stop.
    pre = precheck_sources(cfg=CFG, sources=[TIER1, TIER1B])
    early = precheck_verification(cfg=CFG, verification=OK_VERIFICATION,
                                  date_of_incident="2026-07-20", date_precision="day",
                                  sources=[TIER1, TIER1B])
    ok &= check("a publishable case passes both early exits", pre.publish and early.publish)

    print("\nWhat counts as a disagreement\n")
    # The gates refused for any item in the `disagreements` list, and the model
    # listed there a source's silence and differences in retelling alike. That
    # produced 59 cases marked Disputed, and the publishing circuit breaker
    # tripped on that share. Now the model judges materiality and the
    # expression is a safeguard.

    # 1. The current form: the model's decision on materiality is respected.
    for label, item, keep in [
        ("model says material", {"fact": "robot_model", "material": True,
                                 "detail": "S1 identifies the H1, S2 the G1."}, True),
        ("model says immaterial", {"fact": "other", "material": False,
                                   "detail": "S1 calls it a performance, S2 a routine."}, False),
        ("material but no detail is not dismissed", {"fact": "severity", "material": True}, True),
        # The model's decision is final even when the explanation looks weak.
        # The expression that read `detail` cancelled real contradictions: "This
        # is a contradiction, not merely a difference in wording" died on the
        # word "wording", and "S3 does not mention the injury count" on the
        # silence of the third source. What the model called material stays.
        ("model decides, the regex does not overrule it",
         {"fact": "date", "material": True,
          "detail": "S1 gives the publication date as Feb 8, S3 as Feb 9."}, True),
    ]:
        ok &= check(label, bool(material_disagreements([item])) == keep)

    # 2. Old records are bare strings judged by the expression alone. Every one
    #    is taken from the production audit log, from the cases that stopped
    #    publishing.
    for text, is_real in [
        ("S1 identifies the robot as the Unitree H1, while S2 identifies it as the G1.", True),
        ("S3 describes 'two unoccupied cars crashed into a manned vehicle,' which contradicts "
         "S1 and S2, which describe one unoccupied Zoox robotaxi colliding with a passenger "
         "vehicle.", True),
        ("The sources describe two different incidents: S1 covers a near-miss with a UPS truck, "
         "while S2 covers a separate crash in a parking lot.", True),
        ("S1 reports no collision occurred, while S2 reports an actual crash with property "
         "damage.", True),
        ("S1, S2 and S3 do not specify the robot model; S4 identifies it as H1.", False),
        ("S1 does not mention the injury; S2 says the worker was hospitalised.", False),
        ("S2 omits the company name entirely.", False),
        ("No source provides a precise date for the incident itself.", False),
        ("S1 states calls to traffic police surged from 8:57pm, while S2 states reports began "
         "around 9pm - a minor timing difference.", False),
        ("S1 identifies the location as Cupertino, while S2 describes it as near San Jose - "
         "these are adjacent cities and may refer to the same location.", False),
        ("S4 describes the routine as a 'martial arts routine' while S1 and S3 describe it more "
         "generally as a public performance.", False),
        ("Publication date vs incident date: S4 was published 2026-07-28 while S1 and S2 were "
         "published earlier.", False),
    ]:
        kept = bool(material_disagreements([text]))
        ok &= check(("real: " if is_real else "not a contradiction: ") + text[:58],
                    kept == is_real)

    print("\nWhat the register counts as an incident\n")
    # Three of the four most recent publications turned out not to be
    # incidents: a stock market debut and two partnerships. The adversarial
    # pass has a flag for this and never once raised it, so the line is now in code.
    for label, itype, severity, is_incident in [
        ("collision with injury", "collision", "minor_injury", True),
        ("fatality", "fatality", "fatality", True),
        ("recall with nobody hurt", "recall", "no_harm", True),
        ("near miss", "near_miss", "no_harm", True),
        ("regulator investigation", "investigation", "no_harm", True),
        ("malfunction with nobody hurt", "malfunction", "no_harm", True),
        ("collision where nobody was hurt is still a collision", "collision",
         "no_harm", True),
        ("fire where nobody was hurt", "fire", "no_harm", True),
        ("'injury' with no harm contradicts itself", "injury", "no_harm", False),
        ("stock market debut", "market_debut", "no_harm", False),
        ("business partnership announcement", "business partnership announcement",
         "no_harm", False),
        ("partnership and deployment announcement",
         "partnership and deployment announcement", "no_harm", False),
        ("funding round", "funding_round", "no_harm", False),
        ("product launch", "product launch", "no_harm", False),
        ("'other' with nobody hurt", "other", "no_harm", False),
        ("a free-text type with a real injury", "pedestrian struck and dragged by "
         "autonomous vehicle", "serious_injury", True),
        ("a free-text type with damage", "robot collapse during live demonstration",
         "property_damage", True),
        ("no type at all but somebody was hurt", None, "minor_injury", True),
        ("no type and nobody hurt", None, "no_harm", False),
        ("severity unknown", "collision", None, False),
    ]:
        reason = check_is_incident(itype, severity)
        ok &= check(label + (" is kept" if is_incident else " is refused"),
                    (reason is None) == is_incident)

    # A vocabulary type must not break because of the description around it.
    ok &= check("a described collision still reads as a collision",
                check_is_incident("rear-end collision", "minor_injury") is None)
    ok &= check("'non collision' is not smuggled in by the word collision",
                check_is_incident("business_announcement", "no_harm") is not None)

    print("\nPrivate names\n")
    cleaned, removed = strip_private_names(
        "Maria Gonzalez was struck by the delivery robot outside the campus."
    )
    ok &= check("private individual is removed", "Maria Gonzalez" not in (cleaned or ""))
    kept, _ = strip_private_names(
        "Company spokesperson Daniel Reeves said the fleet was grounded."
    )
    ok &= check("named spokesperson is kept", "Daniel Reeves" in (kept or ""))

    # The name pattern is just two capitalised words, so without these
    # exceptions it removed "Boston Dynamics" and "San Francisco" along with
    # surnames. This is not cosmetic: a vanished company name makes a case about
    # that company meaningless.
    known = {"Boston Dynamics", "Waymo"}
    for text, must_keep in [
        ("A Boston Dynamics robot struck a worker at the plant.", "Boston Dynamics"),
        ("A Waymo vehicle crashed with an suv in San Francisco, CA.", "San Francisco"),
        ("Agility Robotics said the unit stopped after the collision.", "Agility Robotics"),
        ("An employee at Traffic Materials Supplier, Llc was pinned.", "Traffic Materials"),
        ("The robot was deployed at Stanford University last spring.", "Stanford University"),
    ]:
        out, _ = strip_private_names(text, protected=known)
        ok &= check(f"kept: {must_keep}", must_keep in (out or ""))

    mixed, removed_mixed = strip_private_names(
        "A robot made by Nimble Robotics injured John Carter at the depot.", protected=known
    )
    ok &= check("company kept and person removed in the same sentence",
                "Nimble Robotics" in (mixed or "") and "John Carter" not in (mixed or ""))

    # Court texts of 2026-10-22: a capital inside a surname, an initial, a month in the middle
    for text, gone in [
        ("On April 25, 2019, George McGee was driving a Tesla when he dropped his phone.", "McGee"),
        ("Dr. Kelsey A. Walsh used a Globus Excelsius GPS robot to operate on Maxwell D. Nalder "
         "at Merit Health River Oaks in Mississippi.", "Nalder"),
        ("Dr. Kelsey A. Walsh used a Globus Excelsius GPS robot to operate on Maxwell D. Nalder "
         "at Merit Health River Oaks in Mississippi.", "Walsh"),
        ("The plaintiff Dawn May Bunch was injured by the machine.", "Bunch"),
    ]:
        out, _ = strip_private_names(text, protected=known | {"Globus Medical"})
        ok &= check(f"removed: {gone}", gone not in (out or ""))
    for text, must_keep in [
        ("Dr. Kelsey A. Walsh used a Globus Excelsius GPS robot to operate on a patient "
         "at Merit Health River Oaks in Mississippi.", "Globus Excelsius"),
        ("Dr. Kelsey A. Walsh used a robot to operate on a patient at Merit Health River Oaks.", "Merit Health River Oaks"),
        ("The passenger was injured on Rosa L. Jones Drive in Cocoa, Florida.", "Rosa L. Jones Drive"),
        ("The veteran was treated at the Ralph H. Johnson VAMC after the injury.", "Ralph H. Johnson VAMC"),
        ("His wife sued under the Federal Tort Claims Act after he was injured.", "Federal Tort Claims Act"),
        ("A worker was injured near the San Francisco Bay shoreline.", "San Francisco Bay"),
        ("The May Mobility shuttle struck and injured a cyclist.", "May Mobility"),
    ]:
        out, _ = strip_private_names(text, protected=known | {"Globus Medical"})
        ok &= check(f"kept: {must_keep}", must_keep in (out or ""))

    print("\nCourt documents\n")
    # A complaint with its text is a public record; it needs no second outlet.
    COURT = {"url": "https://www.courtlistener.com/docket/1/x-v-y/", "domain": "courtlistener.com",
             "title": "Doe v. Robot Co. (D. Mass., No. 1:26-cv-1)", "published_at": "2026-03-20",
             "tier": 1, "article_text": "COMPLAINT. Plaintiff alleges the surgical robot arm moved unexpectedly. " * 40}
    ok &= check("court document with text is recognised", court_document([COURT]))
    ok &= check("docket without text is not a document",
                not court_document([{**COURT, "article_text": "Docket entry 1."}]))
    pre = precheck_sources(cfg=CFG, sources=[COURT])
    ok &= check("court document alone passes the source precheck", pre.publish)
    alone = evaluate(cfg=CFG, sources=[COURT], verification=OK_VERIFICATION, adversarial=OK_ADVERSARIAL,
                     company="Robot Co.", severity="minor_injury", date_of_incident="2026-01-10",
                     date_precision="day", today=date(2026, 7, 21))
    ok &= check("court document alone publishes a non-grave case", alone.publish)
    low = evaluate(cfg=CFG, sources=[COURT], verification={**OK_VERIFICATION, "verification_score": 0.78},
                   adversarial=OK_ADVERSARIAL, company="Robot Co.", severity="minor_injury",
                   date_of_incident="2026-01-10", date_precision="day", today=date(2026, 7, 21))
    ok &= check("court document alone passes with score 0.78 (court threshold 0.75)", low.publish)
    press_low = evaluate(cfg=CFG, sources=[TIER1, TIER1B], verification={**OK_VERIFICATION, "verification_score": 0.78},
                         adversarial=OK_ADVERSARIAL, company="Robot Co.", severity="minor_injury",
                         date_of_incident="2026-01-10", date_precision="day", today=date(2026, 7, 21))
    ok &= check("press-only case still needs 0.80", not press_low.publish)
    grave = evaluate(cfg=CFG, sources=[COURT], verification=OK_VERIFICATION, adversarial=OK_ADVERSARIAL,
                     company="Robot Co.", severity="fatality", date_of_incident="2026-01-10",
                     date_precision="day", today=date(2026, 7, 21))
    ok &= check("court document: named company with a fatality publishes as an allegation", grave.publish)
    ok &= check("court document: grave rule recorded as waived", grave.checks.get("grave_waived") == "court_document")
    press_grave = evaluate(cfg=CFG, sources=[TIER1, TIER1B], verification=OK_VERIFICATION, adversarial=OK_ADVERSARIAL,
                           company="Robot Co.", severity="fatality", date_of_incident="2026-01-10",
                           date_precision="day", today=date(2026, 7, 21))
    ok &= check("press: named company with a fatality still needs three sources", not press_grave.publish)
    flagged = {**OK_ADVERSARIAL, "risk_score": 0.6, "blocking": [
        {"flag": "named_private_individual", "evidence": "plaintiff named in the complaint"},
        {"flag": "unattributed_accusation", "evidence": "only the complaint alleges it"},
        {"flag": "stale_as_new", "evidence": "incident 2023, filing 2026"}]}
    waived = evaluate(cfg=CFG, sources=[COURT], verification=OK_VERIFICATION, adversarial=flagged,
                      company="Robot Co.", severity="minor_injury", date_of_incident="2023-10-31",
                      date_precision="day", today=date(2026, 7, 21))
    ok &= check("court document: complaint flags and risk 0.6 do not block", waived.publish)
    ok &= check("court document: waived flags are recorded",
                sorted(waived.checks.get("flags_waived") or []) == ["named_private_individual", "stale_as_new", "unattributed_accusation"])
    fake = evaluate(cfg=CFG, sources=[COURT], verification=OK_VERIFICATION,
                    adversarial={**flagged, "blocking": [{"flag": "satire_or_fake", "evidence": "x"}]},
                    company="Robot Co.", severity="minor_injury", date_of_incident="2023-10-31",
                    date_precision="day", today=date(2026, 7, 21))
    ok &= check("court document: other adversarial flags still block", not fake.publish)
    press_flagged = evaluate(cfg=CFG, sources=[TIER1, TIER1B], verification=OK_VERIFICATION, adversarial=flagged,
                             company="Robot Co.", severity="minor_injury", date_of_incident="2023-10-31",
                             date_precision="day", today=date(2026, 7, 21))
    ok &= check("press: the same flags still block", not press_flagged.publish)
    bare = precheck_sources(cfg=CFG, sources=[{**COURT, "article_text": "Docket entry 1."}])
    ok &= check("bare docket entry alone does not pass", not bare.publish)

    print(f"\n{'ALL GATES PASS' if ok else 'GATE TESTS FAILED'}\n")
    return 0 if ok else 1


def test_gates() -> None:
    assert main() == 0


if __name__ == "__main__":
    raise SystemExit(main())
