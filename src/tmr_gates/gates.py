"""Publication gates: deterministic rules that decide whether a verified
incident may be published, and what must be stripped from its public text.

There is deliberately no model here. A model answers "do these sources describe
the same event"; the gates answer "may this be published", and every rule in
them can be read, tested and reproduced: two independent domains, source tiers,
no future dates, three sources and a tier 1 outlet for a death or serious
injury attributed to a named company, blocking flags from the adversarial
pass, a risk ceiling, a separate policy for court records, and a stripper for
the names of private individuals.

Inline comments are in Ukrainian, the working language of the project; the
README documents every rule in English.
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
    """Домени, що лишились після склеювання синдикації.

    Один і той самий текст, перевиданий трьома сайтами холдингу, це одне
    джерело, а не три. Ловимо за схожістю тіла статті: перевидання майже
    ніколи не переписують текст.
    """
    kept: list[tuple[str, str]] = []
    for s in sources:
        domain = (s.get("domain") or "").lower().removeprefix("www.")
        if not domain:
            continue
        # Tier3 не рахується за незалежне підтвердження. Інакше «дві незалежні
        # газети» могли скластися з однієї справжньої і одного reddit-треду, і
        # ворота пропускали б звинувачення, підперте постом у соцмережі.
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


# Розбіжності, які насправді ними не є.
#
# Ворота дискваліфікували справу за БУДЬ-який пункт списку `disagreements`, а
# модель на прохання "перелічи розбіжності" сумлінно перелічувала все: мовчання
# джерела, різницю в переказі, дати публікації статей, округлення часу. Так
# накопичилось 59 справ із публічною позначкою Disputed, і частка перевалила
# поріг, через що пайплайн вимкнув собі публікацію.
#
# Тепер суттєвість оцінює сама модель (`material` у verify.GEN_RULES) - вона
# бачить тексти, а регулярний вираз бачить лише переказ. Вираз лишається
# запобіжником двох призначень: він судить старі записи, зроблені до появи
# поля, і знімає пункти, де модель поставила material=true, але сама ж описала
# розбіжність як мовчання чи дрібницю. Він тільки прибирає, ніколи не додає.
_NOT_A_CONTRADICTION = re.compile(
    r"(?i)("
    # мовчання: тільки два твердження можуть суперечити одне одному
    r"do(?:es)? not (?:specify|mention|name|state|identify|give|provide|report|confirm)"
    r"|not (?:specified|mentioned|named|stated|identified|given|provided|reported)"
    r"|no (?:source )?(?:mention|specifies|provides|gives|states|confirms)"
    r"|without (?:naming|specifying|mentioning)|omits?\b|silent (?:on|about)"
    r"|only .{0,30}(?:mentions|identifies|specifies)"
    r"|lacks? (?:the |a )?(?:detail|specific|mention)"
    # дата публікації статті - не дата події
    r"|publication date|date the article|article'?s? date|when the article"
    r"|published \d|dateline"
    # модель сама назвала розбіжність дрібною або можливо уявною
    r"|minor (?:discrepancy|difference|timing)|slight(?:ly|)? (?:differ|discrepan)"
    r"|may refer to the same|adjacent (?:cities|towns)"
    r"|more generally|a turn of phrase|wording"
    r")"
)


def material_disagreements(disagreements: list) -> list[str]:
    """Лишає тільки ті розбіжності, які є суперечністю двох джерел про факт.

    Приймає обидві форми: словники з полем `material` від нинішньої моделі і
    голі рядки зі старих записів, які судяться самим лише виразом.
    """
    kept = []
    for d in disagreements or []:
        if isinstance(d, dict):
            # Рішення моделі остаточне, і вираз до нього не застосовується.
            #
            # Раніше вираз ішов і по `detail`, "як запобіжник". Але `detail` -
            # це пояснення, і промпт прямо просить написати, чому це є або не є
            # суперечністю. Тому фраза "This is a contradiction, not merely a
            # difference in wording" містила слово "wording" і скасовувала
            # розбіжність про різних виробників; "S3 does not mention the
            # injury count" скасовувала розбіжність про кількість загиблих.
            # Запобіжник, що читає пояснення, скасовує саме те, що пояснюють.
            if d.get("material"):
                kept.append(str(d.get("detail") or d.get("fact") or "unspecified disagreement"))
            continue

        # Старі записи - голі рядки без рішення моделі. Тільки їх і судить вираз.
        text = str(d).strip()
        if not text or _NOT_A_CONTRADICTION.search(text):
            continue
        kept.append(text)
    return kept


# Словник подій, які реєстр веде. Список закритий свідомо: реєстр інцидентів
# знає, що таке інцидент, і все, що в нього не лягає, інцидентом не стає від
# того, що про це написали три видання.
#
# Привід: 3 з 4 останніх публікацій виявились не інцидентами - дебют акцій
# Unitree на біржі, партнерство Serve з Grubhub, партнерство Uber з Lucid і
# Nuro. Реєстр сортується за датою, тому саме це бачив перший відвідувач.
# Адверсарний прохід має для цього прапорець `no_incident` і жодного разу його
# не поставив: risk_score 0.10-0.15, порожній red_flags. Судження моделі тут
# ненадійне, а перелік типів - ні.
INCIDENT_TYPES = {
    "collision", "crash", "malfunction", "injury", "fatality", "death", "fire",
    "near_miss", "entrapment", "runaway", "property_damage",
    # Події без потерпілого, але з дією регулятора чи суду - це теж матеріал
    # реєстру: саме вони показують, чим інцидент закінчився.
    "recall", "investigation", "lawsuit", "settlement", "fine", "citation",
}

# Тяжкість, за якої щось справді сталося. Далі тип уже не питаємо.
HARM_SEVERITIES = {"minor_injury", "serious_injury", "fatality", "property_damage"}

# Подія без потерпілого - це все одно подія: зіткнення, в якому нікого не
# зачепило, лишається зіткненням. Тому для `no_harm` достатньо, щоб тип
# упізнавався зі словника. Виняток - типи, які самі стверджують шкоду: "injury"
# при `no_harm` це не подія, а суперечність у власних свідченнях.
NO_HARM_KEEPS = INCIDENT_TYPES - {"injury", "fatality", "death"}


def incident_type_key(incident_type: str | None) -> str:
    """Звести тип події до одного слова словника, або порожнє, якщо не звівся."""
    text = (incident_type or "").strip().lower().replace("-", "_").replace(" ", "_")
    if text in INCIDENT_TYPES:
        return text
    # Заперечення перед типом скасовує тип. Розбиття по "_" робило з
    # "non_collision" окремий токен "collision", тобто зіткнення, якого не
    # було, зараховувалось як зіткнення - рівно те, від чого цей коментар
    # обіцяв захищати.
    if re.search(r"(?i)\b(non|no|not|without|denied|unconfirmed|alleged)\b", text.replace("_", " ")):
        return ""
    for word in text.split("_"):
        if word in INCIDENT_TYPES:
            return word
    return ""


def check_is_incident(incident_type: str | None, severity: str | None) -> str | None:
    """Причина відмови, якщо це не інцидент. None, якщо інцидент.

    Вирішує тяжкість, а не тип. Тип модель пише вільним текстом, і холостий
    прохід по реєстру показав, чим це закінчується: правило, побудоване на
    типі, знімало з публікації Cruise, який протягнув пішохода двадцять футів
    ("pedestrian struck and dragged by autonomous vehicle" - у словнику такого
    немає), і відкликання ста пʼяти робота-таксі Zoox. Якщо постраждала людина
    або пошкоджено майно, це інцидент, хоч би як його назвали.

    Питати тип має сенс лише там, де не сталося нічого: саме туди й потрапляли
    біржовий дебют і партнерства.
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
    """Чи є серед джерел судовий документ із власним текстом.

    Позовна заява або рішення суду - публічний запис, а не чийсь переказ, тому
    двох незалежних видань до нього не треба: реєстр і обіцяє "дію регулятора
    або суду" як подію. Але лише з текстом: сам рядок у реєстрі суду (назва,
    номер, дата) ще не каже, що сталось."""
    for s in sources:
        domain = (s.get("domain") or "").lower().removeprefix("www.")
        if domain == "courtlistener.com" and len(s.get("article_text") or "") >= 1500:
            return True
    return False


# Прапори адверсарного проходу, які не блокують справу на судовому документі.
COURT_NON_BLOCKING = {"named_private_individual", "unattributed_accusation", "stale_as_new"}


def min_score(cfg: Config, sources: list[dict]) -> float:
    """Поріг верифікації: для справи на судовому документі нижчий.

    Модель оцінює впевненість за згодою джерел між собою; один документ
    без другого джерела чесно отримує близько 0.8 (Velez v. Tesla: 0.82 з
    датою, тяжкістю і компанією), і загальний поріг 0.85 відсік би кожен
    такий позов. Документ сам по собі є первинним записом, тому для нього
    діє court_min_verification_score.
    """
    base = float(cfg["min_verification_score"])
    if court_document(sources):
        return min(base, float(cfg.get("court_min_verification_score") or 0.75))
    return base


def required_domains(cfg: Config, sources: list[dict]) -> int:
    return 1 if court_document(sources) else int(cfg["min_independent_domains"])


def precheck_sources(*, cfg: Config, sources: list[dict]) -> Decision:
    """Умови §8.2, які не залежать від моделі взагалі.

    Це рівно перевірки 2 і 3 з `evaluate`, витягнуті наперед. Джерела з одного
    домену або самі лише tier3 провалять ворота хоч би що сказала модель, тож
    платити за два проходи по такому матеріалу немає сенсу. Строгий підмножинний
    зв'язок з `evaluate` тут важливіший за економію: ця функція має тільки
    відсіювати те, що й так було б відсіяне, і ніколи нічого не дозволяти.
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


# Предмет реєстру - комерційні фізичні роботи й автономні машини. Знахідка
# може пройти всі інші ворота, не маючи до них стосунку: 2026-10-03 швидка
# смуга опублікувала позов родини застреленої агентом ICE, бо дві незалежні
# газети, дата, наслідок і тип "lawsuit" були на місці. Модель відповідає на
# питання про подію, а не про те, чи є в ній робот; це перевіряє код.
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
    """None, якщо в описі події є комерційний робот або автономна машина."""
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

    # 1. Та сама подія
    if not verification.get("same_event"):
        decision.fail("sources do not describe the same event")

    # 2. Незалежні домени (судовий документ з текстом достатній сам по собі)
    domains = independent_domains(sources)
    decision.checks["independent_domains"] = domains
    need = required_domains(cfg, sources)
    decision.checks["court_document"] = need == 1
    if len(domains) < need:
        decision.fail(f"only {len(domains)} independent domain(s), need {need}")

    # 3. Рівні джерел: tier3 ніколи не достатній сам по собі
    tiers = sorted(tier_of(d) for d in domains)
    decision.checks["tiers"] = tiers
    if not tiers or min(tiers) > 2:
        decision.fail("no tier1 or tier2 source among independent domains")

    # Політика для судових документів (Вова, 22.10.2026): позов чи рішення суду
    # є первинним записом звинувачення. Заголовок каже "Lawsuit alleges", імена
    # приватних осіб знімає стрипер, тож правило тяжких, прапори про названих
    # осіб, неатрибутоване звинувачення і "старе як нове" (позов 2026 про подію
    # 2023 з датою події в картці) не блокують, а ризик допускається до
    # court_max_risk_score.
    court = court_document(sources)

    # 4. Посилене правило для звинувачень
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

    # 4b. Це взагалі інцидент
    not_incident = check_is_incident(incident_type, severity)
    decision.checks["incident_type"] = incident_type
    if not_incident:
        decision.fail(not_incident)

    # 5. Суперечності в ключових фактах
    disagreements = material_disagreements(verification.get("disagreements"))
    decision.checks["disagreements"] = disagreements
    if disagreements:
        decision.fail(f"sources disagree on key facts: {'; '.join(disagreements)[:200]}")

    # 6. Пороги
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

    # 7. Блокуючі прапори адверсарного проходу
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

    # 8. Санітарні перевірки дат
    #
    # Реєстр хронологічний: головний графік будується за роком події, і справа,
    # яку не можна розмістити в часі, з нього просто зникає, лишаючись у
    # підсумковому числі. Тому дата обов'язкова, але з точністю до місяця -
    # "у липні" в новинах зустрічається частіше за точне число, і відкидати
    # такі випадки означало б втрачати реальні інциденти заради охайності.
    # Сам рік без місяця замалий: він розтягує подію на дванадцять місяців.
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


# Імена приватних осіб вирізаються кодом, а не лише промптом: промпт можна
# обійти формулюванням, регулярка - ні.
_TITLE_PREFIX = r"(?:Mr|Mrs|Ms|Dr|Prof|Officer|Judge|Sheriff|Sen|Rep|Gov)\.?\s+"
# Два або три слова з великої літери. Три - бо "Regina Allen Elsea" за
# двослівним шаблоном перетворювалась на "a person Elsea", тобто прізвище
# лишалось на сторінці. Ініціал посередині теж рахується за слово.
# Слово імені: з великої літери, з можливою великою всередині (McGee, DeSantis,
# MacArthur) або апострофом (O'Brien). Раніше "George McGee" збігався як
# "George Mc", і на сторінку виходило "a personGee" (TMR-0891, 22.10.2026).
_NAME_TOKEN = r"[A-Z][a-z]{1,15}(?:(?:'|)[A-Z][a-z]{1,15})?"
_NAME = rf"{_NAME_TOKEN}(?:\s+(?:[A-Z]\.|{_NAME_TOKEN}))(?:\s+[A-Z][a-z]{{2,20}}(?:[A-Z][a-z]{{1,15}})?)?"

# Вік поруч з іменем - найсильніша ознака приватної особи в цьому корпусі:
# "Regina Allen Elsea, 20, was killed", "Christopher C. Pardue, 71, died".
# Ловимо і те, чого загальний шаблон не бачить: одне слово ("Ramanjaneyulu")
# і написання без латиниці.
_NAME_WITH_AGE = re.compile(
    r"\b([^\W\d_][\w'\-]{1,20}(?:\s+(?:[A-Z]\.|[^\W\d_][\w'\-]{1,20})){0,2})"
    r"(?=,\s*\d{1,3}\s*,)"
)

# "a 22-year-old trainee engineer Ramanjaneyulu was killed" - вік стоїть перед
# іменем, тому загальний шаблон його не бачить, а слово з великої літери після
# вікової конструкції це майже завжди потерпілий.
# Прапорець нечутливості обмежений групою навмисно: (?i) на весь шаблон робив
# [A-Z] байдужим до регістру, і перший прохід зняв слово "was".
_NAME_AFTER_AGE = re.compile(
    r"(?i:\d{1,3}[- ]year[- ]old\s+(?:[a-z]+\s+){0,3})([A-Z][\w'\-]{2,24})"
)
_PUBLIC_ROLE = re.compile(
    r"(?i)\b(spokesperson|spokesman|spokeswoman|chief executive|ceo|cto|coo|president|"
    r"director|minister|senator|governor|mayor|attorney general|commissioner|judge|"
    r"inspector|prosecutor|official)\b"
)


# Юридичні форми: те, що стоїть поруч, - організація, а не людина.
_CORPORATE = re.compile(
    r"(?i)\b(inc|llc|l\.l\.c|ltd|limited|corp|corporation|co|company|gmbh|ag|s\.?a|"
    r"b\.?v|plc|oy|ab|kk|pte|pty|holdings|group|technologies|robotics|systems|labs|"
    r"motors|automation|industries|university|college|hospital|institute|department|"
    r"administration|agency|commission|police|county|city|state|llp|firm|attorneys?|"
    r"counsel|associates|partners)\b"
)
# Слова, поруч з якими Title Case означає людину, а не машину чи установу.
# Без цієї умови шаблон знімав "Zeekr Rt", "Shanghai Stock Exchange", "On June"
# і перетворював заголовок на "a Zoox autonomous vehicle a person was involved".
# Обіцянку тримає не жадібність шаблону, а те, що всі сильні ознаки людини
# (вік поруч, звертання) обробляються окремо і в контексті не потребують.
_PERSON_CONTEXT = re.compile(
    # Префікси беруться з \w*, а не в межах слова: \binjur\b не збігався з
    # "injured", і правило мовчки не спрацьовувало на найчастішому формулюванні
    # в цьому корпусі.
    r"(?i)\b(?:killed|kills|died|dies|dead|death|fatally|fatality|injur\w*|hurt|"
    r"wounded|hospitalis\w*|hospitaliz\w*|victim\w*|worker\w*|employee\w*|"
    r"technician\w*|engineer\w*|pedestrian\w*|cyclist\w*|patient\w*|passenger\w*|"
    r"toddler|child|children|woman|women|man|men|widow\w*|famil\w*|survived|"
    r"suffer\w*|crush\w*|struck|strikes|drag\w*|pinn\w*|trapp\w*|amputat\w*|"
    r"burn\w*|sued|suing|plaintiff\w*|defendant\w*|estate of|father|mother|son|daughter|"
    r"husband|wife|his |her |"
    # Судові й медичні тексти (позови, 22.10.2026): лікар і пацієнт названі
    # поруч з операцією, а не з "травмою" - "Dr. X used a robot to operate on Y".
    r"surgeon\w*|surgery|operat\w*|doctor\w*|physician\w*|deficit\w*|diagnos\w*|"
    r"treat\w*|underwent|driving|drove|veteran\w*)"
)

# Title Case, який у цьому корпусі майже ніколи не є людиною.
_NOT_A_PERSON = re.compile(
    # Марки й моделі машин ідуть окремим переліком: у титулах NHTSA вони стоять
    # у дужках ("(Hyundai Ioniq 5)") поруч зі словами про потерпілих, тому
    # контекстна умова їх не рятує.
    r"(?i)\b(hyundai|toyota|jaguar|chrysler|ford|honda|zeekr|lucid|kia|nissan|"
    r"chevrolet|tesla|bmw|mercedes|volkswagen|volvo|ioniq|highlander|pacifica|"
    r"i-pace|palletizer|forklift|conveyor|crane|"
    # Топонімічні суфікси: друге слово видає адресу надійніше за будь-який список.
    r"drive|avenue|road|street|boulevard|lane|highway|freeway|parkway|square|"
    r"park|plaza|bridge|tunnel|airport|gigafactory|campus|mall|hollywood|gardens|"
    # Сторони світу починають назви місць, а числівники - переліки машин.
    r"west|east|north|south|three|two|four|five|six|seven|eight|nine|ten|"
    # Країни трапляються в кожному другому заголовку і людьми не є.
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
# Слово одразу після збігу, яке робить з нього назву місця чи закону, а не
# людину: "Rosa L. Jones Drive", "Ralph H. Johnson VAMC", "Federal Tort Claims Act".
_FACILITY_AFTER = re.compile(
    r"^\s+(?:Drive|Road|Street|Avenue|Boulevard|Lane|Highway|Way|Court|VAMC|VA\b|"
    r"Medical|Hospital|Center|Centre|Clinic|Act|Claims|System|Plaza|Park|Bridge|"
    r"Building|County|University|School|Airport|Station|Plant|Facility|Foundation|"
    r"Institute|Memorial|Surgical|Robotics|Technologies|Industries)\b")

# "... in San Francisco, CA" - двобуквений код штату після коми означає місце.
_STATE_CODE = re.compile(r"^\s*,\s*[A-Z]{2}\b")
# Топоніми, які трапляються в цій предметній області щодня і не мають юридичної
# форми поруч. Список свідомо короткий: він доповнює правила, а не замінює їх.
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
        """Службове слово у збігу: "Tesla Model", "Vinci Surgical System". Місяць
        посередині не рахується: "Dawn May Bunch" - людина, хоч May і місяць."""
        toks = unarticled(name).split()
        for i, tok in enumerate(toks):
            if 0 < i < len(toks) - 1 and _MONTH_OR_DAY.match(tok):
                continue
            if _NOT_A_PERSON.search(tok):
                return True
        return False

    # Заголовок у Title Case ("Employee Is Pinned Against Heated Mold By Robotic
    # Arm") складається з великих літер цілком, і загальний шаблон перетворює
    # його на "a person a person a person". Такі рядки судимо лише сильними
    # ознаками: вік поруч і звертання. Саме про це попереджав коментар вище про
    # первинні документи регуляторів.
    words = [w for w in re.findall(r"[A-Za-z][\w'\-]*", text) if len(w) > 2]
    # 0.8, не 0.6: речення позову "Dr. X used a Globus Excelsius GPS robot on
    # Y at Merit Health River Oaks in Mississippi" має 61% великих літер і
    # проходило як Title Case заголовок, тобто без загального проходу.
    title_case = len(words) >= 4 and sum(w[0].isupper() for w in words) / len(words) > 0.8

    def unarticled(name: str) -> str:
        """"The Waymo" - це та сама Waymo, а не людина на прізвище Waymo."""
        return re.sub(r"(?i)^(the|a|an)\s+", "", name).strip()

    def replace(match: re.Match) -> str:
        name = match.group(0)
        # Контекст береться з рядка, по якому йде саме ця заміна (match.string),
        # а не з вихідного text: після першого проходу зміщення вже інші, і
        # "at Merit Health" перевірялось не на тому місці.
        low = unarticled(name).lower()
        if low in protected_lower or low in _KNOWN_PLACES:
            return name
        if any(low.startswith(kp + " ") for kp in _KNOWN_PLACES):
            return name  # "San Francisco Bay", "New York City"
        # Назва компанії всередині збігу теж захищає: "Baidu Apollo" і
        # "Three Waymo" це та сама компанія з зайвим словом поруч.
        if any(pn in low for pn in protected_lower if len(pn) > 3):
            return name
        # Перше слово назви компанії теж захищає: "Globus Excelsius" поруч з
        # "surgery" інакше став би "a person", бо в реєстрі компанія "Globus Medical".
        if any(tok in protected_firsts for tok in low.split()):
            return name
        window = match.string[max(0, match.start() - 90) : match.end() + 90]
        if _PUBLIC_ROLE.search(window):
            return name
        if _not_a_person(name):
            return name
        # Сам по собі Title Case нічого не доводить. Ім'я знімається лише тоді,
        # коли поруч сказано, що з людиною щось сталося.
        if not _PERSON_CONTEXT.search(window):
            return name
        # Юридичну форму шукаємо впритул, а не в широкому вікні: "Amazon" за
        # тридцять символів від імені працівника не робить це ім'я компанією.
        # Юридичну форму шукаємо впритул праворуч. Ліворуч - лише вузький
        # перелік слів про фірму: широкий список тут давав "Nimble Robotics
        # injured John Carter", де назва компанії за два слова захищала людину.
        # Ініціал посередині ("Maxwell D. Nalder") - майже напевно людина:
        # "Health" за кілька слів праворуч ("at Merit Health") цього не скасовує.
        has_initial = re.search(r"\s[A-Z]\.\s", name) is not None
        if not has_initial and _CORPORATE.search(match.string[match.start() : match.end() + 24]):
            return name
        if _FIRM_BEFORE.search(match.string[max(0, match.start() - 20) : match.start()]):
            return name
        # "in East Hollywood", "at Berkman Drive", "near Austin Gigafactory" -
        # прийменник місця перед Title Case означає адресу, а не потерпілого.
        if _PLACE_PREP.search(match.string[: match.start()]):
            return name
        if _STATE_CODE.match(match.string[match.end() :]):
            return name
        if _FACILITY_AFTER.match(match.string[match.end() :]):
            return name
        removed.append(name)
        return "a person"

    def replace_group(match: re.Match) -> str:
        """Те саме рішення, але знімається лише перша група, не весь збіг."""
        name = match.group(1)
        low = unarticled(name).lower()
        # Загальний шаблон уже міг спрацювати тут: без цього "a person, 20,"
        # перетворювалось на "a a person, 20,".
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

    # Вікові конструкції йдуть ПЕРШИМИ, по оригінальному тексту. У зворотному
    # порядку загальний шаблон уже лишав "a person", і віковий бачив у цьому
    # слово "person" як прізвище: виходило "a a person, 20,".
    cleaned = _NAME_WITH_AGE.sub(replace_group, text)
    cleaned = _NAME_AFTER_AGE.sub(replace_group, cleaned)
    cleaned = re.sub(_TITLE_PREFIX + _NAME, replace, cleaned)
    if not title_case:
        cleaned = re.sub(_NAME, replace, cleaned)
    return cleaned, removed
