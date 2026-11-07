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

FEEDS = [
    # (Name, Feed-URLs zum Ausprobieren der Reihe nach)
    ("Hochparterre", ["https://www.hochparterre.ch/rss.xml", "https://www.hochparterre.ch/rss"]),
]

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


def parse_feed(raw: str, name: str) -> list[dict]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        root = ET.fromstring(_fix_xml(raw))
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
        if title and link:
            out.append({"id": "m-" + slug(link)[-60:], "datum": dt, "typ": "Medien", "titel": clean(title),
                        "beschrieb": "", "kanton": None, "gemeinde": None, "frist": None,
                        "quelle": name, "url": link})
    return out


def collect_feeds(offline: Path | None) -> tuple[list[dict], dict]:
    out, status = [], {}
    for name, urls in FEEDS:
        if offline:
            f = offline / f"feed_{slug(name)}.xml"
            if f.exists():
                out += parse_feed(f.read_text(), name)
                status[name] = "offline"
            continue
        status[name] = "fehlt"
        for u in urls:
            try:
                items = parse_feed(fetch(u, "application/rss+xml, application/xml"), name)
                if items:
                    out += items
                    status[name] = f"ok ({len(items)})"
                    break
            except Exception as e:  # noqa: BLE001
                status[name] = f"Fehler: {e}"[:120]
    return out, status


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

    by_id = {m["id"]: m for m in archiv}
    for m in neu:
        by_id[m["id"]] = m
    cutoff = (TODAY - timedelta(days=ARCHIVE_DAYS)).isoformat()
    alle = sorted((m for m in by_id.values() if (m.get("datum") or "") >= cutoff),
                  key=lambda m: m.get("datum") or "", reverse=True)
    # Filter auch aufs Archiv anwenden (Regeln können sich ändern) und Wiederholungs-Publikationen zusammenfassen
    rub_of = {v: k for k, v in TYP.items()}
    def ok(m):
        if m["typ"] == "Medien":
            return True
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
