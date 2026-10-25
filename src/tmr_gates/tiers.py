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
    # Regulators and courts: primary documents, not accounts of them.
    "osha.gov", "nhtsa.gov", "cpsc.gov", "saferproducts.gov", "justice.gov",
    "sec.gov", "ftc.gov", "europa.eu", "gov.uk", "canada.ca",
    "courtlistener.com",  # RECAP/PACER dockets: a primary court record
    # Non-English sources (added 2026-10-23): wire agencies, public broadcasters
    # and national newspapers. Tabloids and Chinese state agencies are left out
    # on purpose: they stay tier 2 and cannot carry a grave case alone.
    # Germany
    "tagesschau.de", "spiegel.de", "faz.net", "sueddeutsche.de", "zeit.de", "dpa.com",
    "handelsblatt.com", "heise.de",
    # France
    "lemonde.fr", "lefigaro.fr", "afp.com", "francetvinfo.fr", "france24.com", "lesechos.fr",
    # Italy
    "ansa.it", "corriere.it", "repubblica.it", "rainews.it", "ilsole24ore.com",
    # Spain
    "elpais.com", "efe.com", "rtve.es", "elmundo.es", "lavanguardia.com",
    # Netherlands
    "nos.nl", "nrc.nl", "volkskrant.nl", "anp.nl", "nu.nl",
    # Poland
    "pap.pl", "tvn24.pl", "wyborcza.pl", "rp.pl", "polsatnews.pl",
    # Japan
    "nhk.or.jp", "www3.nhk.or.jp", "asahi.com", "mainichi.jp", "yomiuri.co.jp", "nikkei.com",
    "kyodonews.jp", "jiji.com",
    # Korea
    "yna.co.kr", "yonhapnews.co.kr", "kbs.co.kr", "chosun.com", "joongang.co.kr", "hani.co.kr",
    "koreaherald.com", "koreatimes.co.kr", "khan.co.kr",
    # Switzerland and Austria (added 2026-10-25, after the first Swiss case
    # arrived with NZZ counted as an unknown regional paper)
    "nzz.ch", "tagesanzeiger.ch", "srf.ch", "rts.ch", "swissinfo.ch", "letemps.ch",
    "orf.at", "derstandard.at", "diepresse.com", "apa.at",
    # China, Hong Kong, Taiwan: independent or international newsrooms
    "scmp.com", "caixin.com", "caixinglobal.com", "cna.com.tw", "sixthtone.com", "rthk.hk",
}

# Domain suffixes of regulators and governments outside the US: primary documents, tier 1.
GOV_SUFFIXES = (
    ".gov", ".gov.uk", ".gouv.fr", ".bund.de", ".gov.it", ".gob.es", ".overheid.nl",
    ".gov.pl", ".go.jp", ".go.kr", ".gov.cn", ".gov.hk", ".gov.tw", ".gov.au", ".gc.ca",
    ".europa.eu", ".admin.ch", ".gv.at", ".gov.sg",
)

TIER3_HINTS = (
    "reddit.com", "medium.com", "substack.com", "blogspot.", "wordpress.",
    "x.com", "twitter.com", "facebook.com", "instagram.com", "youtube.com",
    "tiktok.com", "quora.com", "pinterest.com",
    # Syndication portals. They do not report, they reprint someone else's text,
    # so as corroboration they are worth nothing: it is the same article under
    # another domain, and they were the usual trigger of the
    # single_source_wrappers flag.
    "yahoo.com", "msn.com", "aol.com", "news.google.com", "flipboard.com",
    "newsbreak.com", "smartnews.com", "inkl.com", "headtopics.com", "biztoc.com",
)

# Exact domains that cannot corroborate an incident. Not because they are
# "yellow", but because the register publishes allegations against named
# companies: whatever goes into a case has to survive that company's lawyer.
# A tabloid, or a site that retells someone else's news in its own words, will not.
TIER3_DOMAINS = {
    # Tabloids
    "dailymail.com", "dailymail.co.uk", "nypost.com", "mirror.co.uk",
    "metro.co.uk", "thesun.co.uk", "express.co.uk", "dailystar.co.uk",
    "nydailynews.com", "ibtimes.com", "ibtimes.co.uk", "people.com",
    "the-sun.com", "radaronline.com",
    # Rewrite farms and content farms: no reporting of their own
    "futurism.com", "interestingengineering.com", "techeblog.com",
    "uniladtech.com", "unilad.com", "ladbible.com", "dailydot.com",
    "boredpanda.com", "indy100.com", "motorbiscuit.com", "carscoops.com",
    "techbuzz.ai", "knowyourmeme.com", "gizmochina.com", "wccftech.com",
    "cybernews.com", "tweaktown.com",
}


def tier_of(domain: str | None) -> int:
    """1: agencies, national media, regulators; 2: regional and trade press;
    3: blogs, social networks, tabloids, syndication portals, never enough alone.

    An unknown domain stays tier 2 on purpose. A local paper that alone wrote
    about an incident at a warehouse in its town is the register's main value,
    and requiring it to be on an allow-list would lose exactly what the wire
    agencies do not have.
    """
    if not domain:
        return 3
    d = domain.lower().removeprefix("www.")
    if d in TIER1_DOMAINS or any(d.endswith(s) or d == s.lstrip(".") for s in GOV_SUFFIXES):
        return 1
    # Match by domain, not by substring.
    #
    # `any(h in d ...)` demoted `vox.com`, `linux.com` and `phoenix.com` through
    # the substring `x.com`, taking corroboration away from real outlets. A hint
    # now has to equal the domain or be its suffix at a dot boundary.
    if d in TIER3_DOMAINS or any(
        d == h.rstrip(".") or d.endswith("." + h.rstrip(".")) or
        (h.endswith(".") and h[:-1] in d.split("."))
        for h in TIER3_HINTS
    ):
        return 3

    # An unknown domain stays tier 2 deliberately: there are thousands of
    # regional outlets, listing them in advance is impossible, and demoting every
    # unknown one to tier 3 would switch corroboration off altogether. The cost
    # of this assumption is carried not by this gate but by the tier 1
    # requirement for grave cases with a named company, exactly where a mistake
    # is most expensive.
    return 2
