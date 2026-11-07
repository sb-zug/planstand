#!/usr/bin/env python3
"""Planstand – Sammler.

Holt Meldungen zu Immobilien- und Arealentwicklung in ZG und ZH und schreibt sie
nach site/data/meldungen.json (Archiv, neue Meldungen werden ergänzt).
Nur Python-Standardbibliothek.

  python collector/collect.py                         # live
  python collector/collect.py --offline tests/fixtures  # gegen gespeicherte Rohdaten

Quellen:
  Amtsblatt ZG  https://amtsblatt.zg.ch/api/v1/publications   (Amtsblattportal SECO, REST, ohne Schlüssel)
  Amtsblatt ZH  https://amtsblatt.zh.ch/api/v1/publications   (gleiche Schnittstelle)
  Fachmedien    RSS (siehe FEEDS), nur Titel + Link, kein Text
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

UA = "planstand-collector/0.1 (+https://github.com/sb-zug/planstand; Prototyp)"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "data"
TODAY = date.today()

# ---------------------------------------------------------------- Konfiguration

AMTSBLATT = {
    # Kanton: (Host, Rubriken, die geholt werden). Rubrik BP = Baugesuche; die übrigen werden über Stichworte gefiltert.
    "ZG": "https://amtsblatt.zg.ch",
    "ZH": "https://amtsblatt.zh.ch",
}
LOOKBACK_DAYS = 21      # so weit zurück bei jedem Lauf (Archiv bleibt erhalten)
PAGES = 6               # max. Seiten à 200 pro Kanton
DETAIL_MAX = 250        # max. Volltexte (XML) pro Lauf, nur Baugesuche; gecacht über die Meldungs-ID
ARCHIVE_DAYS = 730      # Meldungen so lange behalten

# Medienmitteilungen & Meldungen per RSS. Felder: Name, URL, Kanton, Gemeinde (oder None), Ort im Text nötig?
# Geprüft mit tools/probe.py (7.11.2026). Fachmedien selbst: kein erlaubter Feed → Medienspiegel von Hand (medienspiegel.json).
FEEDS = [
    # Medienmitteilungen (Kurztext erlaubt)
    ("Stadt Zürich", "https://www.stadt-zuerich.ch/content/web/de/aktuell/medienmitteilungen/jcr:content/mainparsys/teaser.rss",
     "ZH", "Zürich", False, "mm"),
    ("Stadt Winterthur", "https://stadt.winterthur.ch/rss/feed?type=press_release", "ZH", "Winterthur", False, "mm"),
    ("Gemeinde Hünenberg", "https://www.zg.ch/behoerden/gemeinden/hunenberg/de/ftw-news-newslistingblock/news_listing_rss",
     "ZG", "Hünenberg", False, "mm"),
    ("Gemeinde Menzingen", "https://www.zg.ch/behoerden/gemeinden/menzingen/de/ftw-news-newslistingblock/news_listing_rss",
     "ZG", "Menzingen", False, "mm"),
    ("presseportal.ch", "https://www.presseportal.ch/de/rss/presseportal.rss2?langid=1", None, None, True, "mm"),
    # Medien (nur Titel + Link, kein Text)
    ("zentralplus", "https://www.zentralplus.ch/feed/", None, None, True, "medien"),
    ("moneycab", "https://www.moneycab.com/feed/", None, None, True, "medien"),
    ("Korporation Zug", "https://www.korporation-zug.ch/feed/", "ZG", "Zug", False, "mm"),
    # Marktstudien (nur Titel + Link)
    ("IAZI", "https://www.iazicifi.ch/feed/", None, None, False, "markt"),
    ("Wüest Partner", "https://www.wuestpartner.com/ch-de/feed/", None, None, False, "markt"),
    ("Fahrländer Partner", "https://fpre.ch/feed/", None, None, False, "markt"),
    ("Raiffeisen", "https://www.raiffeisen.ch/rch/de/ueber-uns/news/_jcr_content.rss", None, None, False, "markt"),
]

# Newsrooms ohne Feed: neue Links auf der Medien-/News-Seite erkennen (geprüft mit tools/probe.py, 7.11.2026).
# Felder: Name, URL, Kanton/Gemeinde fix (oder None → Ort muss im Text stehen)
NEWSROOMS = [
    ("Halter", "https://www.halter.ch/de/news", None, None),
    ("Losinger Marazzi", "https://www.losinger-marazzi.ch/de/news", None, None),
    ("Swiss Prime Site", "https://www.sps.swiss/de/medien/medienmitteilungen", None, None),
    ("Senn", "https://senn.com/medien/", None, None),
    ("Intershop", "https://www.intershop.ch/de/investoren/investor-relations/medienmitteilungen", None, None),
    ("Zug Estates", "https://zugestates.ch/medien", "ZG", "Zug"),
    ("Avadis", "https://www.avadis.ch/ueber-uns/unternehmen/medien", None, None),
    ("Patrimonium", "https://www.patrimonium.ch/de/news", None, None),
    ("Wincasa", "https://www.wincasa.ch/", None, None),
    ("Zuger Kantonalbank", "https://www.zugerkb.ch/medien", "ZG", None),
]
NEWSROOM_FETCH_MAX = 70   # Artikelseiten pro Lauf
NEWSWEG = re.compile(r"news|medien|media|press|aktuell|mitteilung|insights|blog|beitr", re.I)
DATUM = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(20\d{2})\b")
STADTZUG_NEWS = "https://stadtzug.ch/de/news?content_category=news"

# Medienmitteilungen: nur mit Immobilien-/Planungsbezug
IMMO = re.compile(r"überbauung|ueberbauung|wohnungen|wohnraum|wohnsiedlung|siedlung|areal|neubau|ersatzneubau|"
                  r"gestaltungsplan|bebauungsplan|nutzungsplan|zonenplan|ortsplanung|\bbzo\b|hochhaus|bauprojekt|"
                  r"baubewilligung|baugesuch|architekturwettbewerb|projektwettbewerb|wettbewerb.{0,40}(?:bau|wohn|areal)|"
                  r"spatenstich|grundsteinlegung|aufrichte|bezugsbereit|immobilie|liegenschaft|baurecht|landkauf|"
                  r"genossenschaft|stadtentwicklung|quartierentwicklung|ortsplanung|planauflage|bauland|"
                  r"immobilienmarkt|wohnungsmarkt|mietwohnungen|preisgünstig|bezahlbar|eigentumswohnungen|preisindiz", re.I)
IMMO_TEXT = re.compile(r"überbauung|gestaltungsplan|bebauungsplan|wohnungen|arealentwicklung|ersatzneubau|"
                       r"hochhaus|wohnsiedlung|baurecht", re.I)
LAERM = re.compile(r"\bbrand\b|rauch|polizei|unfall|feuerwehr|fledermä|benennung|budget|steuerfuss|kongress|seminar|"
                   r"\bkurs\b|webinar|release|bewilligte .*baugesuche|baugesuche vom|baugesuche ab|stellen|"
                   r"abstimmungsvorlage|hat abgestimmt|legislatur|ceref|exklusive", re.I)


MARKT_JA = re.compile(r"markt|preis|index|indiz|miet|wohn|büro|bau|immobil|transaktion|landwert|leerstand|rendite|eigentum|"
                      r"logistik|verkauf|nachfrage|angebot", re.I)
MARKT_NEIN = re.compile(r"episode|podcast|partnerschaft|tritt .*aus|menschen hinter|plattform|mit wem|kunde|"
                        r"führt .* mit|bündeln|webinar|seminar|veranstaltung", re.I)


def mm_ok(titel: str, text: str) -> bool:
    if LAERM.search(titel):
        return False
    return bool(IMMO.search(titel) or IMMO_TEXT.search(text))
ORTE_TEXT = re.compile(r"\b(?:Zug|Baar|Cham|Steinhausen|Rotkreuz|Risch|Hünenberg|Oberägeri|Unterägeri|Menzingen|Neuheim|"
                       r"Walchwil|Zürich|Winterthur|Uster|Dübendorf|Dietikon|Wetzikon|Wädenswil|Horgen|Kloten|Opfikon|"
                       r"Thalwil|Adliswil|Schlieren|Regensdorf|Bülach|Illnau-Effretikon|Volketswil|Meilen|Küsnacht|"
                       r"Zollikon|Stäfa|Affoltern|Wallisellen|Dielsdorf|Glattbrugg|Oerlikon|Altstetten)\b")

# Grosse Bauvorhaben (Baugesuche). Regel: GROSS trifft zu, ÄNDERUNG nicht.
#   GROSS = Planungsbegriff (Gestaltungsplan, Arealüberbauung, Hochhaus …)
#        oder ab WOHNUNGEN_MIN Wohnungen
#        oder Neubau mehrerer Wohnhäuser / Neubau eines grossen Nicht-Wohnbaus (Geschäftshaus, Schulanlage …)
WOHNUNGEN_MIN = 8
STRONG = re.compile(r"arealüberbauung|arealbebauung|überbauung|ueberbauung|gestaltungsplan|bebauungsplan|"
                    r"sondernutzungsplan|quartierplan|hochhaus|siedlung", re.I)
NEU = re.compile(r"\b(?:ersatz)?neubau(?:ten)?\b|neubauprojekt|neuüberbauung", re.I)
MEHRERE = re.compile(r"mehrfamilienhäuser|\b(?:[2-9]|\d{2}|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn)\s+"
                     r"(?:mehrfamilienh|wohnhäuser|wohngebäude|wohnbauten|mfh)|wohnhäusern", re.I)
GROSSBAU = re.compile(r"wohn- und geschäftsh|wohn- und gewerbe|geschäftshaus|bürogebäude|büro- und|verwaltungsgebäude|"
                      r"schulanlage|schulhaus|alterszentrum|pflegezentrum|hotel|einkaufszentrum|dienstleistungsgebäude", re.I)
UEBERBAUUNG = re.compile(r"arealüberbauung|arealbebauung|wohnüberbauung|überbauung|ueberbauung", re.I)
KLEIN = re.compile(r"wärmepumpe|photovoltaik|pv-anlage|solaranlage|reklame|fassadensanierung|sanierung|umbau|"
                   r"sichtschutz|pergola|carport|velounterstand|einfriedung|stützmauer|antenne|mobilfunk|pool", re.I)
WOHNUNGEN = re.compile(r"(\d{1,4})\s*(?:wohnungen|wohneinheiten|whg\b)", re.I)
AENDERUNG = re.compile(r"projektänderung|abänderung|änderung zu|nachträglich|grundriss- und fassadenänderung|"
                       r"wiederherstellung|umnutzung einer|liftanbau|lukarne", re.I)


def gross(text: str) -> bool:
    neu = NEU.search(text) or (UEBERBAUUNG.search(text) and not KLEIN.search(text))
    if AENDERUNG.search(text) or not neu:   # ohne Neubau kein grosses Vorhaben (Sanierung, Reklame, PV …)
        return False
    if STRONG.search(text):
        return True
    n = max((int(x) for x in WOHNUNGEN.findall(text)), default=0)
    if n >= WOHNUNGEN_MIN:
        return True
    return bool(NEU.search(text) and (MEHRERE.search(text) or GROSSBAU.search(text)))


# Planung & Politik ausserhalb der Baugesuche (Titel)
PLANUNG = re.compile(r"gestaltungsplan|bebauungsplan|zonenplan|ortsplanung|richtplan|bau- und zonenordnung|bzo\b|"
                     r"sondernutzungsplan|quartierplan|planauflage|öffentliche auflage|mitwirkung|"
                     r"arealentwicklung|überbauung|nutzungsplan|baulinien|landabtausch|baurecht", re.I)
NICHT_PLANUNG = re.compile(r"abwasser|abfall|gebühr|steuer|wald|jagd|fischerei|konzession|parkier|verkehrsanordnung|"
                           r"signalisation|reglement über|friedhof|strasse|trottoir|lärmsanierung|lichtsignal|belag|"
                           r"gewässerr|richtplanung .?verkehr|veloweg|radweg|bushaltestelle|knoten", re.I)
PLAN_STARK = re.compile(r"gestaltungsplan|bebauungsplan|sondernutzungsplan|quartierplan|nutzungsplanung|"
                        r"bau- und zonenordnung|\bbzo\b|zonenplan|ortsplanung|arealentwicklung|überbauung", re.I)
PRIVAT = re.compile(r"testament|erbschaft|erbenruf|verschollen|schuldenruf|konkurs|betreibung|nachlass|"
                    r"kraftloserklärung|einbürgerung|strafbefehl|gerichtlich", re.I)

# Typ je Rubrik-Präfix (Amtsblattportal)
TYP = {"BP": "Baugesuch", "RP": "Raumplanung", "AB": "Abstimmung", "RS": "Politik", "KO": "Gemeinde", "VE": "Kanton"}

# Gemeinden ZG (fix). ZH wird aus Absender/Titel gelesen.
ZG_GEMEINDEN = ["Zug", "Baar", "Cham", "Steinhausen", "Risch", "Hünenberg", "Oberägeri", "Unterägeri",
                "Menzingen", "Neuheim", "Walchwil"]


# ---------------------------------------------------------------- Helfer

def fetch(url: str, accept: str = "*/*", timeout: int = 40) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


def slug(s: str) -> str:
    s = s.lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("é", "e"), ("è", "e"), ("à", "a"), ("ß", "ss")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def clean(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def gemeinde(kanton: str, office: str, title: str) -> str | None:
    """Gemeinde aus Absender («Gemeinde Baar – Bauabteilung», «Stadt Zürich …») oder Titel («…, Walchwil»)."""
    if kanton == "ZG":
        tail = title.rsplit(",", 1)[-1].strip() if "," in title else ""
        for g in ZG_GEMEINDEN:
            if re.search(rf"\b{g}\b", tail):
                return g
        office = re.sub(r"Kanton Zug", "", office)
        for g in ZG_GEMEINDEN:
            if re.search(rf"\b{g}\b", office):
                return g
        return None
    m = re.search(r"(?:Stadt|Gemeinde|Politische Gemeinde|Einwohnergemeinde|Bausekretariat|Bauamt)\s+"
                  r"([A-ZÄÖÜ][\wäöüéè.\- ]+?)(?:\s*[-–,(]|$)", office)
    if m:
        return re.sub(r"^(Stadt|Gemeinde)\s+", "", m.group(1)).strip()
    m = re.search(r",\s*(?:\d{4}\s+)?([A-ZÄÖÜ][\wäöüéè.\- ]+)$", title)
    return m.group(1).strip() if m else None


def xml_text(raw: str) -> tuple[str, str]:
    """Volltext und Projektbeschrieb aus der Publikations-XML (Struktur je Rubrik verschieden → defensiv)."""
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return clean(raw), ""
    parts, desc = [], ""
    for el in root.iter():
        t = (el.text or "").strip()
        if not t:
            continue
        parts.append(t)
        tag = el.tag.split("}")[-1].lower()
        if not desc and any(k in tag for k in ("projectdescription", "description", "bauvorhaben", "project")) and len(t) > 15:
            desc = t
    return clean(" ".join(parts)), clean(desc)[:400]


# ---------------------------------------------------------------- Amtsblatt

def amtsblatt_url(host: str, kanton: str, page: int) -> str:
    q = {
        "publicationStates": "PUBLISHED",
        "cantons": kanton,
        "publicationDate.start": (TODAY - timedelta(days=LOOKBACK_DAYS)).isoformat(),
        "pageRequest.size": "200",
        "pageRequest.page": str(page),
    }
    return f"{host}/api/v1/publications?" + urllib.parse.urlencode(q)


def relevant(rub: str, title: str, full: str = "") -> bool:
    if PRIVAT.search(title):
        return False
    text = f"{title} {full}"
    if rub == "BP":
        return gross(text)
    if rub in ("RP", "AB", "RS", "KO", "VE"):
        if not PLANUNG.search(title):
            return False
        return bool(PLAN_STARK.search(title)) or not NICHT_PLANUNG.search(title)
    return False


def collect_amtsblatt(kanton: str, host: str, known: dict, seen: set, offline: Path | None) -> list[dict]:
    raw_pages = []
    if offline:
        f = offline / f"amtsblatt_{kanton.lower()}.json"
        if f.exists():
            raw_pages.append(json.loads(f.read_text()))
    else:
        for page in range(PAGES):
            data = json.loads(fetch(amtsblatt_url(host, kanton, page), "application/json"))
            raw_pages.append(data)
            if len(data.get("content", [])) < 200:
                break
    out, details = [], 0
    for data in raw_pages:
        for p in data.get("content", []):
            m = p["meta"]
            rub = (m.get("rubric") or "")[:2]
            title = (m.get("title") or {}).get("de") or ""
            if rub not in TYP or PRIVAT.search(title):
                continue
            mid = m["id"]
            old = known.get(mid)
            beschrieb = old.get("beschrieb", "") if old else ""
            full = ""
            # Baugesuche: Titel ist nur die Adresse → Volltext holen (einmal, dann im Archiv)
            if rub == "BP" and not old and mid not in seen and not offline and details < DETAIL_MAX:
                try:
                    full, beschrieb = xml_text(fetch(f"{host}/api/v1/publications/{mid}/xml", "application/xml"))
                    details += 1
                except Exception as e:  # noqa: BLE001
                    print(f"  XML {mid}: {e}", file=sys.stderr)
            if old:
                out.append(old)
                continue
            if mid in seen:          # schon geprüft, nicht relevant
                continue
            if rub != "BP" or full:   # Baugesuch ohne Volltext beim nächsten Lauf nochmals prüfen
                seen.add(mid)
            if not relevant(rub, title, full or beschrieb):
                continue
            office = (m.get("registrationOffice") or {}).get("displayName", "")
            ort = gemeinde(kanton, office, title)
            if ort:   # ZH-Titel enden oft mit «…, Öffentliche Auflage, Gemeinde» → Ende kürzen
                title = re.sub(rf"(,\s*(Öffentliche Auflage|Genehmigung|Festsetzung))*,\s*{re.escape(ort)}\s*$", "", title)
            t = re.sub(r"^((Kommunale\s+)?Baugesuchs?publikation|Bauprojekt):\s*", "", title)
            out.append({
                "id": mid,
                "datum": (m.get("publicationDate") or "")[:10],
                "typ": TYP[rub],
                "titel": t,
                "beschrieb": beschrieb,
                "kanton": kanton,
                "gemeinde": ort,
                "frist": (m.get("expirationDate") or "")[:10] or None,
                "quelle": f"Amtsblatt {kanton}",
                "url": f"{host}/#!/search/publications/detail/{mid}",
            })
    return out


# ---------------------------------------------------------------- Fachmedien (nur Titel + Link)

def _fix_xml(raw: str) -> str:
    """Viele Feeds enthalten HTML-Entities (&nbsp;) oder nackte & – vor dem Parsen bereinigen."""
    raw = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)([a-zA-Z][a-zA-Z0-9]*;)?",
                 lambda m: html.unescape("&" + m.group(1)) if m.group(1) and html.unescape("&" + m.group(1)) != "&" + m.group(1)
                 else "&amp;" + (m.group(1) or ""), raw)
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", raw)


def _parse_feed_loose(raw: str, name: str) -> list[dict]:
    """Rückfall für fehlerhaftes XML: Items per Regex lesen (nur Titel, Link, Datum)."""
    out = []
    for it in re.findall(r"<item\b.*?</item>", raw, re.S)[:40]:
        def g(tag):
            m = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", it, re.S)
            v = (m.group(1) if m else "").strip()
            return re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", v, flags=re.S).strip()
        title, link, d = clean(g("title")), clean(g("link")), g("pubDate")
        desc = clean(g("description"))
        try:
            dt = parsedate_to_datetime(d).date().isoformat()
        except (TypeError, ValueError):
            dt = TODAY.isoformat()
        if title and link.startswith("http"):
            out.append({"id": "m-" + slug(link)[-60:], "datum": dt, "typ": "Medien", "titel": title, "beschrieb": desc,
                        "kanton": None, "gemeinde": None, "frist": None, "quelle": name, "url": link})
    return out


def parse_feed(raw: str, name: str) -> list[dict]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        try:
            root = ET.fromstring(_fix_xml(raw))
        except ET.ParseError:
            return _parse_feed_loose(raw, name)
    out = []
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for it in items[:40]:
        def g(tag):
            el = it.find(tag)
            return (el.text or "").strip() if el is not None and el.text else ""
        title = g("title") or g("{http://www.w3.org/2005/Atom}title")
        link = g("link")
        if not link:
            el = it.find("{http://www.w3.org/2005/Atom}link")
            link = el.get("href", "") if el is not None else ""
        d = g("pubDate") or g("{http://www.w3.org/2005/Atom}updated") or g("{http://www.w3.org/2005/Atom}published")
        try:
            dt = parsedate_to_datetime(d).date().isoformat() if "," in d else d[:10]
        except (TypeError, ValueError):
            dt = TODAY.isoformat()
        desc = g("description") or g("{http://www.w3.org/2005/Atom}summary")
        if title and link:
            out.append({"id": "m-" + slug(link)[-60:], "datum": dt, "typ": "Medien", "titel": clean(title),
                        "beschrieb": clean(desc), "kanton": None, "gemeinde": None, "frist": None,
                        "quelle": name, "url": link})
    return out


def _kurz(text: str, n: int = 260) -> str:
    """Erste Sätze einer Medienmitteilung als Kurztext (amtliche/Firmen-Mitteilungen sind zur Verbreitung bestimmt)."""
    t = clean(text)
    if len(t) <= n:
        return t
    cut = t[:n]
    dot = cut.rfind(". ")
    return (cut[:dot + 1] if dot > 80 else cut.rsplit(" ", 1)[0] + " …")


def mm_items(feed_items: list[dict], name: str, kanton, gem, need_place: bool, art: str = "mm") -> list[dict]:
    out = []
    for it in feed_items:
        text = f"{it['titel']} {it.get('beschrieb', '')}"
        if art == "markt":
            if LAERM.search(it["titel"]) or MARKT_NEIN.search(it["titel"]) or not MARKT_JA.search(it["titel"]):
                continue
            out.append({**it, "id": "mk-" + slug(it["url"])[-70:], "typ": "Marktstudie", "kanton": None, "gemeinde": None,
                        "quelle": name, "beschrieb": ""})
            continue
        if not mm_ok(it["titel"], it.get("beschrieb", "")):
            continue
        g = gem
        if need_place:
            m = ORTE_TEXT.search(text)
            if not m:
                continue
            g = {"Rotkreuz": "Risch", "Oerlikon": "Zürich", "Altstetten": "Zürich", "Glattbrugg": "Opfikon"}.get(m.group(0), m.group(0))
        k = kanton or (("ZG" if g in ZG_GEMEINDEN else "ZH") if g else None)
        if art == "medien":   # Medienartikel: nur Titel + Link
            out.append({**it, "id": "md-" + slug(it["url"])[-70:], "typ": "Medien", "kanton": k, "gemeinde": g,
                        "quelle": name, "beschrieb": ""})
        else:
            out.append({**it, "id": "mm-" + slug(it["url"])[-70:], "typ": "Medienmitteilung", "kanton": k, "gemeinde": g,
                        "quelle": name, "beschrieb": _kurz(it.get("beschrieb", ""))})
    return out


def parse_stadtzug(page: str) -> list[dict]:
    """News der Stadt Zug (HTML-Liste, Parser aus zug.now)."""
    out = []
    for li in re.findall(r"<li\b[^>]*>(.*?)</li>", page, re.S):
        a = re.search(r'<a href="(https://stadtzug\.ch/de/news/20[^"]+)"[^>]*>(.*?)</a>', li, re.S)
        if not a:
            continue
        d = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", li)
        lead = re.search(r'dxp-typo-body[^"]*"[^>]*>(.*?)</div>', li, re.S)
        out.append({"datum": f"{d.group(3)}-{d.group(2)}-{d.group(1)}" if d else TODAY.isoformat(),
                    "titel": clean(a.group(2)), "beschrieb": clean(lead.group(1)) if lead else "", "url": a.group(1),
                    "frist": None})
    return out


def _meta(page: str, prop: str) -> str:
    m = re.search(rf'<meta[^>]+(?:property|name)=["\']{prop}["\'][^>]+content=["\']([^"\']*)', page, re.I) or \
        re.search(rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{prop}["\']', page, re.I)
    return clean(m.group(1)) if m else ""


def harvest(url: str, body: str) -> list[tuple[str, str]]:
    """Kandidaten für Beiträge: Links auf derselben Domain mit News-Pfad und längerem Linktext."""
    host = urllib.parse.urlsplit(url).netloc.replace("www.", "")
    out = []
    for h, t in re.findall(r'<a[^>]+href=["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', body, re.S | re.I):
        full = urllib.parse.urljoin(url, html.unescape(h)).split("?")[0]
        txt = clean(t)
        if urllib.parse.urlsplit(full).netloc.replace("www.", "") != host or len(txt) < 30:
            continue
        if not NEWSWEG.search(full) or full.rstrip("/") == url.rstrip("/") or full.lower().endswith((".jpg", ".png", ".zip")):
            continue
        if re.search(r"/(fr|en|it)(/|$)", urllib.parse.urlsplit(full).path):   # nur deutsche Fassung
            continue
        out.append((full, txt))
    return list(dict(out).items())


MONATE = {"januar": 1, "februar": 2, "märz": 3, "maerz": 3, "april": 4, "mai": 5, "juni": 6, "juli": 7, "august": 8,
          "september": 9, "oktober": 10, "november": 11, "dezember": 12, "january": 1, "february": 2, "march": 3,
          "may": 5, "june": 6, "july": 7, "october": 10, "december": 12}
_MON_RX = "|".join(sorted(MONATE, key=len, reverse=True))


def _datum(*texte: str):
    """Datum finden: ISO (Meta, JSON-LD, <time>), 16.10.2026, 16. Oktober 2026, October 16, 2026."""
    for t in texte:
        t = t or ""
        for rx in (r'"datePublished"\s*:\s*"(20\d{2})-(\d{2})-(\d{2})', r'<time[^>]+datetime=["\'](20\d{2})-(\d{2})-(\d{2})',
                   r'^(20\d{2})-(\d{2})-(\d{2})'):
            m = re.search(rx, t)
            if m:
                return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        sichtbar = re.sub(r"<(script|style)\b.*?</\1>", " ", t, flags=re.S | re.I)
        sichtbar = re.sub(r"<[^>]+>", " ", sichtbar)
        m = DATUM.search(sichtbar)
        if m and 1 <= int(m.group(2)) <= 12:
            return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
        m = re.search(rf"\b(\d{{1,2}})\.?\s+({_MON_RX})\s+(20\d{{2}})", sichtbar, re.I)
        if m:
            return f"{m.group(3)}-{MONATE[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
        m = re.search(rf"\b({_MON_RX})\s+(\d{{1,2}}),\s+(20\d{{2}})", sichtbar, re.I)
        if m:
            return f"{m.group(3)}-{MONATE[m.group(1).lower()]:02d}-{int(m.group(2)):02d}"
    return None


def newsroom_item(name, kanton, gem, href, linktext, page):
    titel = _meta(page, "og:title") or linktext
    titel = re.sub(r"\s*[|–-]\s*" + re.escape(name) + r".*$", "", titel, flags=re.I).strip() or linktext
    desc = _meta(page, "og:description") or _meta(page, "description")
    datum = _datum(_meta(page, "article:published_time"), linktext, page)
    return {"id": "nr-" + slug(href)[-70:], "datum": datum, "titel": titel, "beschrieb": desc, "url": href,
            "frist": None, "bild": og_image(page, href)}


BRANCHE = re.compile(r"kapitalerhöhung|ergebnis|halbjahr|jahresabschluss|portfolio|übernimmt|übernahme|kauft|verkauft|"
                     r"akquisition|anleihe|strategie|ernennt|wechsel in der|ceo|cfo|anlagevermögen|wettbewerb|fonds|"
                     r"anlagegruppe|anlagestiftung|bewertung|transaktion|immobilienmarkt|neue mandate|zusammenarbeit", re.I)
NR_NEIN = re.compile(r"sommerfest|safety week|markenauftritt|^medienmitteilungs?$|finanz-news|medienkonferenz|^media$|"
                     r"tiny house|apéro|jubiläum|lehrling|lernende", re.I)
ADJ = {"Zuger": ("ZG", None), "Zürcher": ("ZH", None)}


def newsroom_einordnen(it: dict, name: str, kanton, gem):
    """Regional (Ort in ZG/ZH) → Medienmitteilung; sonst Unternehmens-/Marktnews → Branche; sonst verwerfen."""
    text = f"{it['titel']} {it.get('beschrieb', '')}"
    if NR_NEIN.search(it["titel"]) or LAERM.search(it["titel"]):
        return None
    m = ORTE_TEXT.search(text)
    if m or gem:
        g = gem or {"Rotkreuz": "Risch", "Oerlikon": "Zürich", "Altstetten": "Zürich", "Glattbrugg": "Opfikon"}.get(m.group(0), m.group(0))
        k = kanton or ("ZG" if g in ZG_GEMEINDEN else "ZH")
        return {**it, "id": "nr-" + slug(it["url"])[-70:], "typ": "Medienmitteilung", "kanton": k, "gemeinde": g,
                "quelle": name, "beschrieb": _kurz(it.get("beschrieb", ""))}
    a = re.search(r"\b(Zuger|Zürcher)\b", text)
    if a or BRANCHE.search(text) or IMMO_TEXT.search(text):
        k = ADJ[a.group(1)][0] if a else kanton
        return {**it, "id": "nr-" + slug(it["url"])[-70:], "typ": "Branche", "kanton": k, "gemeinde": None,
                "quelle": name, "beschrieb": _kurz(it.get("beschrieb", ""))}
    return None


def collect_newsrooms(offline: Path | None) -> tuple[list[dict], dict]:
    if offline:
        return [], {}
    f = OUT / "newsrooms.json"
    state = json.loads(f.read_text()) if f.exists() else {}
    out, status, fetched, debug = [], {}, 0, {}
    for name, url, kanton, gem in NEWSROOMS:
        try:
            links = harvest(url, fetch(url, "text/html"))
        except Exception as e:  # noqa: BLE001
            status[name] = f"Fehler: {e}"[:120]
            continue
        seen = set(state.get(url, []))
        erstmals = url not in state
        neu = [(h, t) for h, t in links if h not in seen][: (6 if erstmals else 8)]
        n = 0
        for h, t in neu:
            if fetched >= NEWSROOM_FETCH_MAX:
                break
            fetched += 1
            dbg = debug.setdefault(name, [])
            try:
                it = newsroom_item(name, kanton, gem, h, t, fetch(h, "text/html"))
            except Exception as e:  # noqa: BLE001
                dbg.append(f"{t[:60]} → Fehler {e}"[:140])
                continue
            if not it["datum"]:
                if erstmals:
                    dbg.append(f"{it['titel'][:70]} → kein Datum")
                    continue
                it["datum"] = TODAY.isoformat()
            if it["datum"] < (TODAY - timedelta(days=120)).isoformat():
                dbg.append(f"{it['titel'][:70]} → alt {it['datum']}")
                continue
            bild = it.pop("bild")
            items = mm_items([it], name, kanton, gem, need_place=gem is None)
            dbg.append(f"{it['titel'][:70]} {it['datum']} → {'ok' if items else 'kein Immo-/Ortsbezug'}")
            for x in items:
                x["bild"] = bild
            out += items
            n += len(items)
        state[url] = list(dict.fromkeys([h for h, _ in links] + list(seen)))[:600]
        status[name] = f"ok ({len(links)} Links, {n} relevant)"
    f.write_text(json.dumps(state, ensure_ascii=False))
    (OUT / "newsroom_debug.json").write_text(json.dumps(debug, ensure_ascii=False, indent=1))
    return out, status


def collect_feeds(offline: Path | None) -> tuple[list[dict], dict]:
    out, status = [], {}
    sources = [(n, u, k, g, p, a, parse_feed) for n, u, k, g, p, a in FEEDS]
    sources.append(("Stadt Zug", STADTZUG_NEWS, "ZG", "Zug", False, "mm", lambda raw, _n: parse_stadtzug(raw)))
    for name, url, kanton, gem, need_place, art, parser in sources:
        try:
            if offline:
                f = offline / f"feed_{slug(name)}.xml"
                if not f.exists():
                    continue
                raw = f.read_text()
            else:
                raw = fetch(url, "application/rss+xml, application/xml, text/html")
            items = mm_items(parser(raw, name), name, kanton, gem, need_place, art)
            out += items
            status[name] = f"ok ({len(items)} relevant)"
        except Exception as e:  # noqa: BLE001
            status[name] = f"Fehler: {e}"[:120]
    # Medienspiegel (Fachmedien): von Hand/Claude gepflegt, nur Titel + Link
    f = OUT / "medienspiegel.json"
    if f.exists():
        for m in json.loads(f.read_text()).get("artikel", []):
            out.append({"id": "ms-" + slug(m["url"])[-70:], "datum": m["datum"], "typ": "Medien", "titel": m["titel"],
                        "beschrieb": m.get("notiz", ""), "kanton": m.get("kanton"), "gemeinde": m.get("gemeinde"),
                        "frist": None, "quelle": m["medium"], "url": m["url"]})
    return out, status


# ---------------------------------------------------------------- Bilder (nur Medienmitteilungen)

BILDER_MAX = 40   # neue og:image-Abrufe pro Lauf


def og_image(page: str, base: str):
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)', page, re.I) or \
        re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image', page, re.I)
    if not m:
        return None
    u = urllib.parse.urljoin(base, html.unescape(m.group(1)))
    return u if u.startswith("https://") and not re.search(r"logo|wappen|favicon|default", u, re.I) else None


def add_images(items: list[dict], offline: bool) -> None:
    """Bild der Medienmitteilung verlinken (nicht kopieren), Quelle wird angezeigt."""
    n = 0
    for m in items:
        if m.get("typ") not in ("Medienmitteilung", "Branche") or "bild" in m:
            continue
        if offline or n >= BILDER_MAX:
            continue
        n += 1
        try:
            m["bild"] = og_image(fetch(m["url"], "text/html"), m["url"])
        except Exception:  # noqa: BLE001
            m["bild"] = None


# ---------------------------------------------------------------- Zuordnung zu Projekten

def match_projects(items: list[dict], projekte: list[dict]) -> None:
    for it in items:
        text = f"{it['titel']} {it.get('beschrieb', '')}".lower()
        hits = []
        for p in projekte:
            if it.get("gemeinde") and p.get("gemeinde") and it["gemeinde"] != p["gemeinde"] and it["typ"] != "Medien":
                continue
            if any(k and k.lower() in text for k in p.get("keywords", [])):
                hits.append(p["slug"])
        it["projekte"] = hits


# ---------------------------------------------------------------- Main

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", type=Path)
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)

    f_meld = OUT / "meldungen.json"
    archiv = json.loads(f_meld.read_text()).get("meldungen", []) if f_meld.exists() else []
    known = {m["id"]: m for m in archiv}
    projekte = json.loads((OUT / "projekte.json").read_text())["projekte"]
    status = {}
    f_seen = OUT / "gesehen.json"
    seen = set(json.loads(f_seen.read_text())) if f_seen.exists() else set()

    neu = []
    for kt, host in AMTSBLATT.items():
        try:
            items = collect_amtsblatt(kt, host, known, seen, args.offline)
            neu += items
            status[f"Amtsblatt {kt}"] = f"ok ({len(items)} relevant)"
        except Exception as e:  # noqa: BLE001  – Quelle fällt aus → alter Stand bleibt
            status[f"Amtsblatt {kt}"] = f"Fehler: {e}"[:160]
            print(f"Amtsblatt {kt}: {e}", file=sys.stderr)
    feeds, fstat = collect_feeds(args.offline)
    status.update(fstat)
    neu += feeds
    nr, nstat = collect_newsrooms(args.offline)
    status.update(nstat)
    neu += nr

    by_id = {m["id"]: m for m in archiv}
    for m in neu:
        alt = by_id.get(m["id"])
        if alt and "bild" in alt:
            m["bild"] = alt["bild"]
        by_id[m["id"]] = m
    cutoff = (TODAY - timedelta(days=ARCHIVE_DAYS)).isoformat()
    alle = sorted((m for m in by_id.values() if (m.get("datum") or "") >= cutoff),
                  key=lambda m: m.get("datum") or "", reverse=True)
    # Filter auch aufs Archiv anwenden (Regeln können sich ändern) und Wiederholungs-Publikationen zusammenfassen
    rub_of = {v: k for k, v in TYP.items()}
    def ok(m):
        if m["typ"] == "Marktstudie":
            return not MARKT_NEIN.search(m["titel"]) and bool(MARKT_JA.search(m["titel"]))
        if m["typ"] == "Branche" or m.get("id", "").startswith(("ms-", "nr-")):
            return True
        if m["typ"] in ("Medien", "Medienmitteilung"):
            return mm_ok(m["titel"], m.get("beschrieb", ""))
        return relevant(rub_of.get(m["typ"], ""), m["titel"], m.get("beschrieb", ""))
    seen_key, dedup = set(), []
    for m in alle:
        if not ok(m):
            continue
        k = (m.get("kanton"), m["titel"].lower(), (m.get("beschrieb") or "")[:80].lower())
        if k in seen_key:
            continue
        seen_key.add(k)
        dedup.append(m)
    alle = dedup
    add_images(alle, bool(args.offline))
    match_projects(alle, projekte)

    f_meld.write_text(json.dumps({"stand": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                                  "meldungen": alle}, ensure_ascii=False, indent=1))
    if not args.offline:
        f_seen.write_text(json.dumps(sorted(seen)[-30000:]))
    (OUT / "meta.json").write_text(json.dumps({"lauf": datetime.now(timezone.utc).isoformat(timespec="minutes"),
                                               "quellen": status, "anzahl": len(alle)}, ensure_ascii=False, indent=1))
    print(json.dumps(status, ensure_ascii=False, indent=1))
    print(f"{len(alle)} Meldungen im Archiv")


if __name__ == "__main__":
    main()
