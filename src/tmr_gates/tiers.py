"""Source tiers: which domains count as primary, which never count as corroboration.

Tier 1: wire agencies, national outlets, public broadcasters, regulators and
courts. Tier 2: everything unknown, deliberately, because regional papers are
where most incidents first appear. Tier 3: social networks, blogs, tabloids and
syndication portals that republish other people's text; they are never enough
on their own and are not counted as independent corroboration.
"""
from __future__ import annotations

TIER1_DOMAINS = {
    "reuters.com", "apnews.com", "bloomberg.com", "bbc.com", "bbc.co.uk", "ft.com",
    "wsj.com", "nytimes.com", "washingtonpost.com", "theguardian.com", "cnbc.com",
    "npr.org", "abcnews.go.com", "cbsnews.com", "nbcnews.com", "cnn.com",
    "latimes.com", "sfchronicle.com", "politico.com", "axios.com",
    # Регулятори і суди: первинні документи, а не переказ
    "osha.gov", "nhtsa.gov", "cpsc.gov", "saferproducts.gov", "justice.gov",
    "sec.gov", "ftc.gov", "europa.eu", "gov.uk", "canada.ca",
    "courtlistener.com",  # докети RECAP/PACER: первинний судовий документ
    # Неангломовні джерела (пакет NLnet/EA Funds, з 23.10.2026): агенції,
    # суспільні мовники й національні газети. Таблоїди й державні агенції
    # Китаю свідомо не тут: вони лишаються tier 2 і не можуть підтверджувати
    # тяжкий випадок самі.
    # Німеччина
    "tagesschau.de", "spiegel.de", "faz.net", "sueddeutsche.de", "zeit.de", "dpa.com",
    "handelsblatt.com", "heise.de",
    # Франція
    "lemonde.fr", "lefigaro.fr", "afp.com", "francetvinfo.fr", "france24.com", "lesechos.fr",
    # Італія
    "ansa.it", "corriere.it", "repubblica.it", "rainews.it", "ilsole24ore.com",
    # Іспанія
    "elpais.com", "efe.com", "rtve.es", "elmundo.es", "lavanguardia.com",
    # Нідерланди
    "nos.nl", "nrc.nl", "volkskrant.nl", "anp.nl", "nu.nl",
    # Польща
    "pap.pl", "tvn24.pl", "wyborcza.pl", "rp.pl", "polsatnews.pl",
    # Японія
    "nhk.or.jp", "www3.nhk.or.jp", "asahi.com", "mainichi.jp", "yomiuri.co.jp", "nikkei.com",
    "kyodonews.jp", "jiji.com",
    # Корея
    "yna.co.kr", "yonhapnews.co.kr", "kbs.co.kr", "chosun.com", "joongang.co.kr", "hani.co.kr",
    "koreaherald.com", "koreatimes.co.kr",
    # Китай, Гонконг, Тайвань: незалежні або міжнародні редакції
    "scmp.com", "caixin.com", "caixinglobal.com", "cna.com.tw", "sixthtone.com",
}

# Суфікси доменів регуляторів і урядів поза США: первинні документи, tier 1.
GOV_SUFFIXES = (
    ".gov", ".gov.uk", ".gouv.fr", ".bund.de", ".gov.it", ".gob.es", ".overheid.nl",
    ".gov.pl", ".go.jp", ".go.kr", ".gov.cn", ".gov.hk", ".gov.tw", ".gov.au", ".gc.ca",
    ".europa.eu", ".admin.ch", ".gv.at", ".gov.sg",
)

TIER3_HINTS = (
    "reddit.com", "medium.com", "substack.com", "blogspot.", "wordpress.",
    "x.com", "twitter.com", "facebook.com", "instagram.com", "youtube.com",
    "tiktok.com", "quora.com", "pinterest.com",
    # Портали-ретранслятори. Вони не повідомляють, а передруковують чужий текст,
    # тому як підтвердження не варті нічого: це та сама стаття під іншим доменом,
    # і саме через них найчастіше спрацьовував прапор single_source_wrappers.
    "yahoo.com", "msn.com", "aol.com", "news.google.com", "flipboard.com",
    "newsbreak.com", "smartnews.com", "inkl.com", "headtopics.com", "biztoc.com",
)

# Точні домени, які не можуть підтверджувати інцидент. Не тому що «жовті», а
# тому що реєстр публікує звинувачення на адресу названих компаній: те, що йде
# в справу, має витримати юриста цієї компанії. Таблоїд або сайт, який переказує
# чужу новину своїми словами, цього не витримає.
TIER3_DOMAINS = {
    # Таблоїди
    "dailymail.com", "dailymail.co.uk", "nypost.com", "mirror.co.uk",
    "metro.co.uk", "thesun.co.uk", "express.co.uk", "dailystar.co.uk",
    "nydailynews.com", "ibtimes.com", "ibtimes.co.uk", "people.com",
    "the-sun.com", "radaronline.com",
    # Переписувачі й контент-ферми: власного репортажу не ведуть
    "futurism.com", "interestingengineering.com", "techeblog.com",
    "uniladtech.com", "unilad.com", "ladbible.com", "dailydot.com",
    "boredpanda.com", "indy100.com", "motorbiscuit.com", "carscoops.com",
    "techbuzz.ai", "knowyourmeme.com", "gizmochina.com", "wccftech.com",
    "cybernews.com", "tweaktown.com",
}


def tier_of(domain: str | None) -> int:
    """1 - агенції, національні медіа, регулятори; 2 - регіональні і галузеві;
    3 - блоги, соцмережі, таблоїди, ретранслятори: самі по собі ніколи не досить.

    Невідомий домен лишається tier2 навмисно. Місцева газета, яка одна написала
    про інцидент на своєму складі, - головна цінність реєстру, і вимагати від неї
    потрапити в білий список означало б втратити саме те, чого немає в агенцій.
    """
    if not domain:
        return 3
    d = domain.lower().removeprefix("www.")
    if d in TIER1_DOMAINS or any(d.endswith(s) or d == s.lstrip(".") for s in GOV_SUFFIXES):
        return 1
    # Збіг за доменом, а не за підрядком.
    #
    # `any(h in d ...)` демотував `vox.com`, `linux.com` і `phoenix.com` через
    # підрядок `x.com`, тобто відбирав корроборацію у справжніх видань. Хінт
    # тепер має збігтися з доменом або бути його суфіксом на межі крапки.
    if d in TIER3_DOMAINS or any(
        d == h.rstrip(".") or d.endswith("." + h.rstrip(".")) or
        (h.endswith(".") and h[:-1] in d.split("."))
        for h in TIER3_HINTS
    ):
        return 3

    # Невідомий домен лишається tier 2 свідомо: регіональних видань тисячі, і
    # перелічити їх наперед неможливо, а демотувати всі невідомі до tier 3
    # означало б вимкнути корроборацію взагалі. Ціну цього припущення несуть
    # не ці ворота, а вимога tier 1 для тяжких випадків з названою компанією -
    # саме там, де помилка коштує найдорожче.
    return 2
