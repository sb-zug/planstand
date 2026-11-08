#!/usr/bin/env python3
"""Planstand – Build. Rendert statische Seiten aus site/data/*.json nach _site/ (SEO, ohne JavaScript nötig).

  python collector/build.py

Seiten: Start, /projekte/, /projekte/<slug>/, /orte/, /orte/<kanton>/<gemeinde>/, /meldungen/,
sitemap.xml, rss.xml (+ RSS pro Ort). Eigene Domain: SITE_URL und BASE anpassen (BASE = "/").
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
from datetime import date, datetime, timezone
from email.utils import format_datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE, DATA, OUT = ROOT / "site", ROOT / "site" / "data", ROOT / "_site"
NAME = "Planstand"
CLAIM = "Immobilien- und Arealentwicklung in der Schweiz"
SITE_URL = os.environ.get("SITE_URL", "https://sb-zug.github.io/planstand")
BASE = os.environ.get("BASE_PATH", "/planstand/")
TODAY = date.today()

PHASEN = ["Planung", "Mitwirkung", "Parlament", "Abstimmung", "Bewilligung", "Bau", "Bezug"]
MON = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.", "Dez."]
KANTONE = {"AG": "Aargau", "AI": "Appenzell Innerrhoden", "AR": "Appenzell Ausserrhoden", "BE": "Bern", "BL": "Basel-Landschaft",
           "BS": "Basel-Stadt", "FR": "Freiburg", "GE": "Genf", "GL": "Glarus", "GR": "Graubünden", "JU": "Jura", "LU": "Luzern",
           "NE": "Neuenburg", "NW": "Nidwalden", "OW": "Obwalden", "SG": "St. Gallen", "SH": "Schaffhausen", "SO": "Solothurn",
           "SZ": "Schwyz", "TG": "Thurgau", "TI": "Tessin", "UR": "Uri", "VD": "Waadt", "VS": "Wallis", "ZG": "Zug", "ZH": "Zürich"}
KT = {k: f"Kanton {v}" for k, v in KANTONE.items()}
AKTIV = ("ZH", "ZG")  # Kantone mit Datenabdeckung (Ausbau Kanton um Kanton)

e = html.escape


def slug(s: str) -> str:
    s = (s or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("é", "e"), ("è", "e"), ("à", "a")):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def u(path: str) -> str:
    return BASE + path.lstrip("/")


def dlabel(s: str) -> str:
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", s or "")
    if m:
        return f"{int(m[3])}. {MON[int(m[2]) - 1]} {m[1]}"
    m = re.fullmatch(r"(\d{4})-(\d{2})", s or "")
    if m:
        return f"{MON[int(m[2]) - 1]} {m[1]}"
    return s or ""


def mdate(s: str):
    """Meilenstein-Datum date (Monat/Jahr = Ende) oder None."""
    s = str(s or "")
    for rx, f in ((r"(\d{4})-(\d{2})-(\d{2})", lambda g: date(*map(int, g))),
                  (r"(\d{4})-(\d{2})", lambda g: date(int(g[0]), int(g[1]), 28)),
                  (r"(\d{4})", lambda g: date(int(g[0]), 12, 31))):
        m = re.fullmatch(rx, s)
        if m:
            return f(m.groups())
    return None


# ---------------------------------------------------------------- Layout

def page(path: str, title: str, desc: str, body: str, rss: str | None = None) -> None:
    full = f"{title} · {NAME}" if title != NAME else f"{NAME} – {CLAIM}"
    canon = SITE_URL.rstrip("/") + "/" + path.lstrip("/")
    feed = f'<link rel="alternate" type="application/rss+xml" title="{e(full)}" href="{u(rss)}">' if rss else ""
    doc = f"""<!doctype html><html lang="de-CH"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(full)}</title><meta name="description" content="{e(desc)}">
<link rel="canonical" href="{e(canon)}"><meta property="og:title" content="{e(full)}">
<meta property="og:description" content="{e(desc)}"><meta property="og:type" content="website">
<link rel="preconnect" href="https://fonts.bunny.net"><link rel="stylesheet" href="https://fonts.bunny.net/css?family=schibsted-grotesk:400,500,600,700,800|ibm-plex-mono:400,500&display=swap">
<link rel="stylesheet" href="{u('assets/app.css')}">{feed}
<link rel="alternate" type="application/rss+xml" title="{NAME} – alle Meldungen" href="{u('rss.xml')}">
</head><body>
<div class="plankopf"><div class="wrap"><span>Wochenbrief Nr. {TODAY.isocalendar()[1]:02d} · KW {TODAY.isocalendar()[1]:02d}/{TODAY.year}</span><span class="pk-hide">47°10′ N · 8°31′ E</span><span>Stand {TODAY.strftime("%d.%m.%Y")}</span><span>Schweiz · Daten ZG, ZH</span></div></div>
<header class="top"><div class="wrap"><a class="logo" href="{u('')}"><i aria-hidden="true">{LOGO}</i>{NAME}</a><span class="claim">Was in der Schweiz geplant, entwickelt und gebaut wird</span>
<nav><a href="{u('artikel/')}" class="nl">Wochenbrief</a><a href="{u('projekte/')}">Projekte</a><a href="{u('kantone/')}">Kantone</a><a href="{u('termine/')}">Termine</a><a href="{u('meldungen/')}">News</a></nav></div></header>
<main class="wrap">{body}</main>
<footer class="foot"><div class="wrap"><p><b>{NAME}</b> sammelt automatisch amtliche Publikationen, Medienmitteilungen und
Projektinformationen zur Immobilien- und Arealentwicklung in der Schweiz. Datenabdeckung derzeit Kantone Zürich und Zug,
weitere Kantone folgen. Massgebend sind die verlinkten
Originalquellen. Medienberichte werden nur verlinkt. Prototyp, Stand {dlabel(TODAY.isoformat())}.</p>
<p><a href="{u('newsletter/')}">Newsletter</a> · <a href="{u('baugesuche/')}">Baugesuch-Radar</a> · <a href="{u('kantone/')}">Kantone</a> · <a href="{u('projekt-melden/')}">Projekt melden</a> · <a href="{u('rss.xml')}">RSS</a> · <a href="{u('ueber/')}">Über Planstand</a></p></div></footer>
</body></html>"""
    f = OUT / path.lstrip("/")
    if path.endswith("/") or path == "":
        f = f / "index.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(doc)
    PAGES.append(path)


PAGES: list[str] = []
LOGO = "".join(f'<b class="{c}"></b>' for c in "nnnnnoonnoonnnnn")


def phasebar(ph: int) -> str:
    cells = "".join(f'<li class="ph{i} {"done" if i < ph else "now" if i == ph else ""}">{p}</li>'
                    for i, p in enumerate(PHASEN, 1))
    return f'<ol class="phases" aria-label="Phase {ph} von 7: {PHASEN[ph - 1]}">{cells}</ol>'


def next_step(p: dict):
    for m in p.get("meilensteine", []):
        d = mdate(m.get("datum"))
        if d is None or d >= TODAY:
            return m
    return None



def bald(m: dict) -> bool:
    """Termin innerhalb der nächsten 12 Monate (für «Nächste Entscheide»)."""
    d = mdate(m.get("datum"))
    return bool(d) and d <= date.fromordinal(TODAY.toordinal() + 365)


def planbild(p: dict, H: int = 250) -> str:
    """Projektbild, sonst Situationsplan im Architekturstil (deterministisch aus dem Slug)."""
    if p.get("bild"):
        cr = f'<span class="credit">Bild: {e(p.get("bild_credit", ""))}</span>' if p.get("bild_credit") else ""
        return f'<img src="{e(p["bild"])}" alt="" loading="lazy">{cr}'
    import random
    r = random.Random(p["slug"])
    W = 400
    sid = re.sub(r"[^a-z0-9]", "", p["slug"])[:20] or "p"
    ang = r.choice([-14, -9, -5, 6, 10])
    out = []
    # Umgebung: Nachbarblöcke (hell), Raster aus Strassen
    for gx in range(-60, W + 60, 92):
        for gy in range(-60, H + 60, 78):
            if r.random() < .82:
                w, h = r.randint(46, 70), r.randint(36, 58)
                out.append(f'<rect class="nb" x="{gx + r.randint(4, 14)}" y="{gy + r.randint(4, 12)}" width="{w}" height="{h}"/>')
                if r.random() < .6:
                    out.append(f'<rect class="nh" x="{gx + r.randint(10, 20)}" y="{gy + r.randint(10, 18)}" width="{r.randint(14, 30)}" height="{r.randint(10, 22)}"/>')
    hood = f'<g transform="rotate({ang} {W / 2} {H / 2})">{"".join(out)}</g>'
    px, py, pw, ph = 70, (H - 140) // 2 - 6, 250, 140
    ry = py + ph + r.randint(18, 40)
    road = (f'<path class="rd" d="M-20 {ry} C 120 {ry - 40}, 260 {ry + 30}, 420 {ry - 10}"/>'
            f'<path class="rdl" d="M-20 {ry} C 120 {ry - 40}, 260 {ry + 30}, 420 {ry - 10}"/>')
    # Projektperimeter + Gebäude
    bld = []
    x = px + 16
    while x < px + pw - 40:
        w = r.randint(28, 52)
        h = r.randint(36, 96)
        y = py + r.randint(10, ph - h - 8) if ph - h - 8 > 10 else py + 10
        lvl = r.choice(["b1", "b2", "b2", "b3"])
        bld.append(f'<rect class="sh" x="{x + 5}" y="{y - 5}" width="{w}" height="{h}"/><rect class="{lvl}" x="{x}" y="{y}" width="{w}" height="{h}"/>')
        if r.random() < .5 and h > 50:
            bld.append(f'<line class="fl" x1="{x}" y1="{y + h / 2}" x2="{x + w}" y2="{y + h / 2}"/>')
        x += w + r.randint(10, 22)
    trees = "".join(f'<circle class="tr" cx="{r.randint(px - 30, px + pw + 30)}" cy="{r.choice([py - 10, py + ph + 12, r.randint(py, py + ph)])}" r="{r.choice([4, 5, 6])}"/>'
                    for _ in range(26))
    proj = (f'<g transform="rotate({ang} {W / 2} {H / 2})"><rect class="pa" x="{px}" y="{py}" width="{pw}" height="{ph}"/>'
            f'{trees}{"".join(bld)}<rect class="per" x="{px - 8}" y="{py - 8}" width="{pw + 16}" height="{ph + 16}"/></g>')
    defs = (f'<defs><pattern id="h{sid}" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            f'<line x1="0" y1="0" x2="0" y2="5" class="hl"/></pattern>'
            f'<pattern id="g{sid}" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M20 0H0V20" class="gl"/></pattern></defs>'
            f'<style>#s{sid} .b1,#s{sid} .b2,#s{sid} .b3{{fill:url(#h{sid})}}</style>')
    return (f'<svg id="s{sid}" class="plan ph{p.get("phase", 3)}" viewBox="0 0 {W} {H}" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Situationsplan, schematisch">'
            f'{defs}<rect class="bg" width="{W}" height="{H}"/><rect width="{W}" height="{H}" fill="url(#g{sid})"/>{hood}{road}{proj}'
            f'<g class="n"><path d="M{W - 22} 12 l6 16 l-6 -5 l-6 5 z"/><text x="{W - 22}" y="40">N</text></g>'
            f'<g class="sc"><rect x="14" y="{H - 14}" width="24" height="4"/><rect class="o" x="38" y="{H - 14}" width="24" height="4"/>'
            f'<rect x="62" y="{H - 14}" width="24" height="4"/><text x="92" y="{H - 9}">0 – 100 m · Schema</text></g></svg>')


CH_SVG = ('<svg class="ch" viewBox="0 0 102 70" role="img" aria-label="Schweizer Karte: Zürich und Zug erfasst">'
          '<path class="land" d="M1.3 56 L4.4 42.5 L13.2 28.9 L22 13.6 L27.5 11.9 L37.4 9.2 L50.6 7.8 L59.4 1.7 L66 6.8 L79.2 11.9 '
          'L81.4 25.5 L88 28.9 L100 34 L99 44.2 L91.3 42.5 L81.4 52.7 L74.8 45.9 L68.2 68.7 L62.7 59.5 L56.1 47.6 L48.4 54.4 L42.9 65.6 '
          'L24.2 65.6 L19.8 49.3 L6.6 52.7 Z"/><path class="kzh" d="M54 7.5 L60 4.5 L66.5 7.5 L67 18 L60 20.5 L55 18 Z"/>'
          '<path class="kzg" d="M55.5 21.5 L60.5 21.5 L60.5 26.5 L55.5 26.5 Z"/></svg>')

FILTER_JS = """<script>
(function(){var f=document.querySelectorAll('.filter select'),l=document.getElementById('plist'),c=document.getElementById('pcnt');if(!l)return;
function run(){var v={};f.forEach(function(s){v[s.dataset.f]=s.value});var r=[].slice.call(l.children),n=0;
r.forEach(function(a){var ok=(!v.kt||a.dataset.kt===v.kt)&&(!v.ph||a.dataset.ph===v.ph)&&(!v.art||a.dataset.art===v.art);a.hidden=!ok;if(ok)n++});
var k=v.sort==='ph'?function(a,b){return b.dataset.ph-a.dataset.ph}:v.sort==='az'?function(a,b){return a.dataset.az<b.dataset.az?-1:1}:function(a,b){return a.dataset.next<b.dataset.next?-1:1};
r.sort(k).forEach(function(a){l.appendChild(a)});c.textContent=n}
f.forEach(function(s){s.addEventListener('change',run)})})();
</script>"""


def card(p: dict) -> str:
    n = next_step(p)
    nxt = f'<p class="next"><b>{e(dlabel(n["datum"]))}</b> {e(n["text"])}</p>' if n else ""
    return (f'<a class="card ph{p["phase"]}" href="{u("projekte/" + p["slug"] + "/")}"><span class="tag">{e(p["gemeinde"])}, '
            f'{e(PHASEN[p["phase"] - 1])}</span><h3>{e(p["titel"])}</h3><p>{e(p.get("untertitel", ""))}</p>{nxt}</a>')


def board(projekte: list[dict], titel: str, sub: str) -> str:
    """Phasen-Tafel; nur Phasen mit Projekten (keine leeren Spalten)."""
    cols, n = "", 0
    for i, ph in enumerate(PHASEN, 1):
        ps = [p for p in projekte if p["phase"] == i]
        if not ps:
            continue
        n += 1
        items = "".join(f'<a href="{u("projekte/" + p["slug"] + "/")}">{e(p["titel"])}'
                        + (f'<small>{e(dlabel(x["datum"]))}</small>' if (x := next_step(p)) and mdate(x["datum"]) else "")
                        + "</a>" for p in ps)
        cols += f'<section class="col ph{i}" aria-label="{ph}"><header>{ph}<span>{len(ps)}</span></header>{items}</section>'
    return (f'<section class="board"><h1>{e(titel)}</h1><p class="sub">{e(sub)}</p>'
            f'<div class="cols" style="--n:{n}">{cols}</div></section>')


def ortkachel(k: str, o: dict) -> str:
    """Kachel für die Ortswahl: Name, Zahl, Phasen-Streifen."""
    ps = o["p"]
    seg = "".join(f'<i class="ph{i}" style="flex:{c}" title="{PHASEN[i - 1]}: {c}"></i>'
                  for i in range(1, 8) if (c := sum(1 for p in ps if p["phase"] == i)))
    return (f'<a class="ort" href="{u("orte/" + k + "/")}"><b>{e(o["name"])}</b><span>{KT[o["kanton"]]}</span>'
            f'<span class="bar">{seg}</span><span>{len(ps)} Projekte · {len(o["m"])} Meldungen</span></a>')


def kantkachel(kt: str, ps: list, n_orte: int) -> str:
    """Kachel für einen Kanton (Ebene 2): Name, Zahlen, Phasen-Streifen."""
    seg = "".join(f'<i class="ph{i}" style="flex:{c}" title="{PHASEN[i - 1]}: {c}"></i>'
                  for i in range(1, 8) if (c := sum(1 for p in ps if p["phase"] == i)))
    return (f'<a class="ort" href="{u("kantone/" + kt.lower() + "/")}"><b>{e(KANTONE[kt])}</b><span>{kt}</span>'
            f'<span class="bar">{seg}</span><span>{len(ps)} Projekte · {n_orte} Orte</span></a>')


def _cut(t: str, n: int) -> str:
    return t if len(t) <= n else t[:n].rsplit(" ", 1)[0] + " …"


def amt_titel(m: dict) -> str:
    """Amtsblatt-Titel lesbar machen: Verfahrens-Anhängsel und Gemeinde am Ende weg."""
    t = re.sub(r"^(Kommunale Nutzungsplanung\.\s*|Bauprojekt:\s*)", "", m["titel"])
    g = re.escape((m.get("gemeinde") or "§§").split()[0].rstrip("."))
    for _ in range(6):
        t = re.sub(rf"(,?\s*(Öffentliche Auflage|Genehmigung|Festsetzung|Bekanntmachung des Inkrafttretens)|,\s*{g}[\w .\-]*)\s*$",
                   "", t).strip()
    t = re.sub(r"\s*\((Kat\.|KTN)[^)]*\)", "", t)
    return t


WOHN = re.compile(r"(\d{1,4})\s*(?:wohnungen|wohneinheiten)", re.I)
ZAHLW = {"zwei": 2, "drei": 3, "vier": 4, "fünf": 5, "sechs": 6, "sieben": 7, "acht": 8, "neun": 9, "zehn": 10}


def wohnungen(m: dict) -> int:
    return max((int(x) for x in WOHN.findall(m.get("beschrieb") or "")), default=0)


def bg_titel(m: dict) -> str:
    """Schlagzeile für ein Baugesuch: Zahl voran, Ort dazu."""
    b, ort = m.get("beschrieb") or "", m.get("gemeinde") or ""
    n = wohnungen(m)
    if n:
        return f"{n} neue Wohnungen in {ort}"
    h = re.search(r"(\d+|zwei|drei|vier|fünf|sechs|sieben|acht|neun|zehn)\s+(mehrfamilienh\w*|wohnhäuser\w*|mfh)", b, re.I)
    if h:
        k = h.group(1).lower()
        return f"{ZAHLW.get(k, k)} neue Wohnhäuser in {ort}"
    for rx, t in ((r"wohn- und geschäftsh", "Neues Wohn- und Geschäftshaus"), (r"wohn- und gewerbe", "Neuer Wohn- und Gewerbebau"),
                  (r"überbauung", "Neue Überbauung"), (r"hochhaus", "Neues Hochhaus"), (r"schul", "Neubau für die Schule"),
                  (r"hotel", "Neues Hotel"), (r"büro|geschäftshaus", "Neues Geschäftshaus")):
        if re.search(rx, b, re.I):
            return f"{t} in {ort}"
    return f"Grösseres Bauvorhaben in {ort}"


def plan_titel(m: dict) -> str:
    """Schlagzeile für eine Planung aus dem Amtsblatt."""
    t, ort = amt_titel(m), m.get("gemeinde") or ""
    roh = m["titel"].lower()
    status = ("liegt öffentlich auf" if "auflage" in roh else "ist in Kraft" if "inkrafttreten" in roh
              else "ist genehmigt" if "genehmigung" in roh else "ist festgesetzt" if "festsetzung" in roh else "")
    name = re.search(r"[«„\"]([^»“\"]+)[»“\"]", t)
    if "gestaltungsplan" in roh:
        return f"{ort}: Gestaltungsplan «{name.group(1)}» {status}".strip() if name else f"{ort}: Gestaltungsplan {status}".strip()
    if "bebauungsplan" in roh:
        return f"{ort}: Bebauungsplan «{name.group(1)}» {status}".strip() if name else f"{ort}: Bebauungsplan {status}".strip()
    if re.search(r"nutzungsplanung|bzo|zonenplan|ortsplanung", roh):
        art = "Teilrevision der Nutzungsplanung" if "teilrevision" in roh else "Revision der Nutzungsplanung"
        if name:
            art += f" «{name.group(1)}»"
        if "nichtgenehmigung" in roh:
            return f"{ort}: Kanton genehmigt {art} nur teilweise"
        return f"{ort}: {art} {status}".strip()
    return f"{ort}: {t}"


def headline(m: dict) -> tuple[str, str]:
    """Schlagzeile + Zusatz. Baugesuche: Beschrieb als Titel, Adresse als Zusatz."""
    if m["typ"] == "Baugesuch":
        return bg_titel(m), _cut(f'{amt_titel(m)} · {m.get("beschrieb") or ""}', 170)
    if m["quelle"].startswith("Amtsblatt"):
        return plan_titel(m), ""
    sub = m.get("beschrieb") or ""
    return m["titel"], ("" if sub.strip().lower().startswith(m["titel"].strip().lower()[:40]) else sub)


def kicker(m: dict, ort=True) -> str:
    wo = f'{e(m["gemeinde"])}, ' if ort and m.get("gemeinde") else ""
    return (f'<span class="typ">{e(m["typ"])}</span><span>{wo}{e(dlabel(m["datum"]))}</span>'
            f'<span>Quelle: {e(m["quelle"])}</span>')


def mrow(m: dict, ort=True) -> str:
    h, sub = headline(m)
    ext = ""
    return (f'<li class="t-{slug(m["typ"])}"><span class="meta">{kicker(m, ort)}</span>'
            f'<a href="{e(m["url"])}" rel="noopener" target="_blank">{e(h)}{ext}</a>'
            + (f'<span class="d">{e(sub)}</span>' if sub else "") + "</li>")


def mlist(items, ort=True, empty="Zurzeit keine Meldungen.") -> str:
    return f'<ul class="mlist">{"".join(mrow(m, ort) for m in items)}</ul>' if items else f'<p class="note">{empty}</p>'


# ---------------------------------------------------------------- Seiten

def build() -> None:
    projekte = json.loads((DATA / "projekte.json").read_text())["projekte"]
    md = DATA / "meldungen.json"
    meldungen = json.loads(md.read_text())["meldungen"] if md.exists() else []
    if OUT.exists():
        shutil.rmtree(OUT)
    shutil.copytree(SITE, OUT)

    for p in projekte:
        p["kslug"] = f'{p["kanton"].lower()}/{slug(p["gemeinde"])}'
    orte: dict[str, dict] = {}
    for p in projekte:
        orte.setdefault(p["kslug"], {"name": p["gemeinde"], "kanton": p["kanton"], "p": [], "m": []})["p"].append(p)
    for m in meldungen:
        if m.get("gemeinde") and m.get("kanton"):
            k = f'{m["kanton"].lower()}/{slug(m["gemeinde"])}'
            orte.setdefault(k, {"name": m["gemeinde"], "kanton": m["kanton"], "p": [], "m": []})["m"].append(m)

    amtlich = [m for m in meldungen if m["typ"] != "Medien"]
    medien = [m for m in meldungen if m["typ"] == "Medien"]
    aktiv = sorted(projekte, key=lambda p: (mdate((next_step(p) or {}).get("datum")) or date(2100, 1, 1)))

    # Start (Magazin)
    artikel = json.loads((DATA / "artikel.json").read_text())["artikel"] if (DATA / "artikel.json").exists() else []
    artikel.sort(key=lambda a: a["datum"], reverse=True)
    news = [m for m in meldungen if m["typ"] in ("Medienmitteilung", "Medien", "Raumplanung", "Marktstudie", "Branche")]
    bg = [m for m in meldungen if m["typ"] == "Baugesuch"]
    bg30 = [m for m in bg if m["datum"] >= (TODAY.fromordinal(TODAY.toordinal() - 30)).isoformat()]
    wohn30 = sum(wohnungen(m) for m in bg30)
    termine = sorted(((mdate(n["datum"]), p, n) for p in projekte if (n := next_step(p)) and mdate(n["datum"]) and bald(n)),
                     key=lambda t: t[0])[:6]
    def dblock(n: dict, first=False) -> str:
        d = mdate(n["datum"])
        top, bot = (f"{d.day}.", MON[d.month - 1]) if re.fullmatch(r"\d{4}-\d{2}-\d{2}", n["datum"]) else (MON[d.month - 1], str(d.year))
        return f'<span class="dat{" hi" if first else ""}"><b>{e(top)}</b>{e(bot)}</span>'

    def nxt_txt(p: dict) -> str:
        n = next_step(p)
        return f'{dlabel(n["datum"])}' if n else "offen"

    # 1 Leitartikel = aktueller Wochenbrief
    lead_p, leit = None, ""
    if artikel:
        a0 = artikel[0]
        lead_p = next((p for p in projekte if p["slug"] in a0.get("projekte", [])), None)
        bildp = lead_p or {"slug": a0["slug"], "phase": 3}
        sb = ""
        if lead_p:
            fk = "".join(f'<div><b>{e(v)}</b><span>{e(k)}</span></div>' for k, v in lead_p.get("fakten", [])[:3])
            sb = (f'<aside class="lsb"><span class="kl">Im Fokus</span><b class="lt">{e(lead_p["titel"])}</b>{fk}'
                  f'<div><b>{e(PHASEN[lead_p["phase"] - 1])}</b><span>Phase</span></div>'
                  f'<a href="{u("projekte/" + lead_p["slug"] + "/")}">Zum Projekt →</a></aside>')
        leit = (f'<section class="leit"><article class="ltxt"><span class="kl"><i></i>Leitartikel · Wochenbrief KW {TODAY.isocalendar()[1]:02d} · {e(dlabel(a0["datum"]))}</span>'
                f'<h1><a href="{u("artikel/" + a0["slug"] + "/")}">{e(a0["titel"])}</a></h1><p>{e(a0["lead"])}</p>'
                f'<div class="lbtn"><a class="btn sig" href="{u("artikel/" + a0["slug"] + "/")}">Leitartikel lesen →</a>'
                f'<a class="btn ghost" href="{u("artikel/")}">Frühere Wochenbriefe</a></div>'
                f'<a class="abo" href="{u("newsletter/")}"><span>Wochenbrief jeden Montag per Mail</span><b>Abonnieren →</b></a></article>'
                f'<div class="lvis"><a class="vis" href="{u("artikel/" + a0["slug"] + "/")}" tabindex="-1" aria-hidden="true">{planbild(bildp, 420)}</a>{sb}</div></section>')

    # 2 Highlights: Projekte aus dem Wochenbrief, dann nächste Entscheide
    hl = ([p for p in projekte if artikel and p["slug"] in artikel[0].get("projekte", [])]
          + [p for p in aktiv if next_step(p)])
    seen, high = set(), []
    for p in hl:
        if p["slug"] not in seen:
            seen.add(p["slug"])
            high.append(p)
    high = high[:4]
    def fakt1(p):
        f = p.get("fakten") or []
        return f'<span>{e(f[0][0]).upper()}<b>{e(f[0][1])}</b></span>' if f else f'<span>NUTZUNG<b>{e(p.get("art") or "")}</b></span>'
    high_html = "".join(
        f'<a class="hcard" href="{u("projekte/" + p["slug"] + "/")}"><span class="vis">{planbild(p)}'
        f'<span class="badge">{p["kanton"]} · {e(PHASEN[p["phase"] - 1])}</span></span>'
        f'<span class="hb"><b>{e(p["titel"])}</b><small>{e(p["gemeinde"])} · {e(p.get("untertitel", ""))}</small>'
        f'<span class="hf">{fakt1(p)}<span>NÄCHSTER SCHRITT<b>{e(nxt_txt(p))}</b></span></span></span></a>' for p in high)

    # 3 Alle Projekte mit Filter
    arten = sorted({(p.get("art") or "").split(" ")[0].strip(",&") for p in projekte if p.get("art")})
    def opts(vals):
        return "".join(f'<option value="{e(v)}">{e(l)}</option>' for v, l in vals)
    filt = (f'<form class="filter" aria-label="Projekte filtern">'
            f'<label>Kanton<select data-f="kt"><option value="">Alle</option>{opts((k, KANTONE[k]) for k in AKTIV)}</select></label>'
            f'<label>Phase<select data-f="ph"><option value="">Alle Phasen</option>{opts((str(i), ph) for i, ph in enumerate(PHASEN, 1))}</select></label>'
            f'<label>Nutzung<select data-f="art"><option value="">Alle Nutzungen</option>{opts((a, a) for a in arten)}</select></label>'
            f'<label>Sortierung<select data-f="sort"><option value="next">Nächster Entscheid</option><option value="ph">Phase</option><option value="az">A–Z</option></select></label></form>')
    def prow(i, p):
        segs = "".join(f'<i class="{"d" if j < p["phase"] else "n" if j == p["phase"] else ""}"></i>' for j in range(1, 8))
        nd = mdate((next_step(p) or {}).get("datum")) or date(2100, 1, 1)
        art = (p.get("art") or "").split(" ")[0].strip(",&")
        return (f'<a class="prow" href="{u("projekte/" + p["slug"] + "/")}" data-kt="{p["kanton"]}" data-ph="{p["phase"]}" data-art="{e(art)}" '
                f'data-next="{nd.isoformat()}" data-az="{e(slug(p["titel"]))}"><span class="pn"><b>{e(p["titel"])}</b><small>{e(p["gemeinde"])}</small></span>'
                f'<span class="pk">{p["kanton"]}</span><span class="pa">{e(p.get("art") or "")}</span>'
                f'<span class="pp"><span class="seg">{segs}</span><small>{e(PHASEN[p["phase"] - 1])}</small></span>'
                f'<span class="px">{e(nxt_txt(p))}</span></a>')
    rows = "".join(prow(i, p) for i, p in enumerate(aktiv))
    liste = (f'<section class="alle" id="projekte"><div class="sh"><h2>Alle Projekte</h2><span class="cnt"><b id="pcnt">{len(projekte)}</b> Projekte · ZG + ZH</span></div>{filt}'
             f'<div class="ptab"><div class="phead"><span>Projekt</span><span>Kt.</span><span>Nutzung</span><span>Phase</span><span>Nächster Schritt</span></div>'
             f'<div id="plist">{rows}</div></div><a class="more" href="{u("projekte/")}">Alle Projekte nach Phase</a></section>')

    term_html = "".join(f'<li>{dblock(n, i == 0)}<span><a href="{u("projekte/" + p["slug"] + "/")}">{e(p["titel"])}</a>'
                        f'<small>{e(p["gemeinde"])} · {e(n["text"])}</small></span></li>'
                        for i, (_, p, n) in enumerate(termine[:5]))
    entw = "".join(f'<li><a href="{e(m["url"])}" rel="noopener" target="_blank">{e(headline(m)[0])}</a>'
                   f'<small>{e(m.get("gemeinde") or m["quelle"])} · {e(dlabel(m["datum"]))}</small></li>' for m in news[:5])
    kz_k = "".join(f'<li><a href="{u("kantone/" + kt.lower() + "/")}"><i class="k{kt.lower()}"></i>{e(KANTONE[kt])}</a>'
                   f'<span>{sum(1 for p in projekte if p["kanton"] == kt)} Projekte</span></li>' for kt in AKTIV)
    aside = (f'<aside class="side2"><section><div class="sh"><h2>Nächste Termine</h2><a href="{u("termine/")}">Alle →</a></div>'
             f'<ul class="termine">{term_html}</ul></section>'
             f'<section><div class="sh"><h2>Kantone</h2><a href="{u("kantone/")}">Alle →</a></div>{CH_SVG}'
             f'<ul class="kliste">{kz_k}<li class="off">+ {26 - len(AKTIV)} Kantone in Vorbereitung</li></ul></section>'
             f'<section><div class="sh"><h2>News</h2><a href="{u("meldungen/")}">Alle →</a></div><ul class="entw">{entw}</ul></section>'
             f'<a class="melden" href="{u("projekt-melden/")}">+ Projekt melden<small>Medienmitteilung senden oder Projekt eintragen</small></a></aside>')

    body = (leit
            + f'<section class="high"><div class="sh"><h2>Highlights</h2><span class="cnt">Grosse Projekte mit Bewegung</span></div><div class="hgrid">{high_html}</div></section>'
            + f'<div class="row4">{liste}{aside}</div>' + FILTER_JS)
    page("", NAME, f"{CLAIM}: Projekte, Entscheide und Termine der Immobilien- und Arealentwicklung, jede Woche neu.",
         body, "rss.xml")

    # Termine
    alle = sorted(((mdate(m["datum"]), p, m) for p in projekte for m in p.get("meilensteine", [])
                   if mdate(m.get("datum")) and mdate(m["datum"]) >= TODAY), key=lambda t: t[0])
    tl = "".join(f'<li>{dblock(m, i == 0)}<span><a href="{u("projekte/" + p["slug"] + "/")}">{e(p["titel"])}</a>'
                 f'<small>{e(p["gemeinde"])} · {e(m["text"])}</small></span></li>' for i, (_, p, m) in enumerate(alle))
    page("termine/", "Termine", "Nächste Termine und Entscheide der Immobilien- und Arealentwicklung in Zug und Zürich.",
         f'<p class="crumb">Übersicht</p><h1>Termine</h1><p class="lead">Informationsanlässe, Parlamentsdebatten, Abstimmungen und '
         f'Meilensteine aller Projekte, chronologisch.</p><section class="termine voll"><ul>{tl}</ul></section>')

    # Artikel
    for a in artikel:
        fett = lambda t: re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e(t))
        txt = "".join("<p>" + fett(t) + "</p>" for t in a.get("absaetze", []))
        if a.get("top"):  # Wochenbrief: Zahlen der Woche, Top 5, Einordnung
            zl = "".join(f'<div class="kz"><b>{e(z["wert"])}</b><span>{e(z["text"])}</span></div>' for z in a.get("zahlen", []))
            tp = "".join(f'<li><span class="meta">{e(t.get("ort", ""))}</span><h3>{e(t["titel"])}</h3><p>{fett(t["text"])}</p>'
                         + (f'<a href="{e(t["quelle"][1])}" rel="noopener" target="_blank">{e(t["quelle"][0])}</a>' if t.get("quelle") else "")
                         + "</li>" for t in a["top"])
            txt = ((f'<h2 class="sh">Zahlen der Woche</h2><div class="wb-zahlen">{zl}</div>' if zl else "")
                   + f'<h2 class="sh">Die {len(a["top"])} wichtigsten Entwicklungen</h2><ol class="wb-top">{tp}</ol>'
                   + (f'<h2 class="sh">Einordnung</h2>{txt}' if txt else ""))
        q = "".join(f'<li><a href="{e(b)}" rel="noopener" target="_blank">{e(l)}</a></li>' for l, b in a.get("quellen", []))
        rel = "".join(card(p) for p in projekte if p["slug"] in a.get("projekte", []))
        page(f'artikel/{a["slug"]}/', a["titel"], a["lead"],
             f'<article class="artikel"><span class="rubrik">{e(a["rubrik"])}</span> <span class="meta" style="display:inline-flex">{e(dlabel(a["datum"]))}, Redaktion Planstand</span>'
             f'<h1>{e(a["titel"])}</h1><p class="lead">{e(a["lead"])}</p>{txt}<h3>Quellen</h3><ul class="links">{q}</ul></article>'
             + (f'<section><h2>Projekte in diesem Artikel</h2><div class="grid">{rel}</div></section>' if rel else ""))
    page("artikel/", "Wochenbrief", "Der Planstand-Wochenbrief: die wichtigsten Entwicklungen und Zahlen der Immobilien- und Arealentwicklung in der Schweiz.",
         "<h1>Wochenbrief</h1>" + "".join(f'<article class="hero-a small"><span class="rubrik">{e(a["rubrik"])}</span> <span class="meta" style="display:inline-flex">{e(dlabel(a["datum"]))}</span>'
                                      f'<h2><a href="{u("artikel/" + a["slug"] + "/")}">{e(a["titel"])}</a></h2><p>{e(a["lead"])}</p></article>' for a in artikel))

    # Baugesuch-Radar
    page("baugesuche/", "Baugesuch-Radar", "Grössere Baugesuche in den Kantonen Zug und Zürich: neue Wohnungen, Überbauungen, Geschäftshäuser.",
         f'<h1>Baugesuch-Radar</h1><p class="lead">Grössere Baugesuche aus den Amtsblättern Zug und Zürich: Neubauten ab 8 Wohnungen, '
         f'mehrere Wohnhäuser, Überbauungen und grosse Geschäftsbauten. In den letzten 30 Tagen: <b>{wohn30} Wohnungen</b> in {len(bg30)} Gesuchen.</p>'
         f'{mlist(bg[:200])}')

    # Projekt melden
    page("projekt-melden/", "Projekt melden", "Projektentwickler, Eigentümer und Vermarkter: Medienmitteilung senden oder Projekt eintragen.",
         '<article class="artikel"><h1>Projekt melden</h1><p class="lead">Sie entwickeln, bauen oder vermarkten ein Projekt in Zug oder Zürich? '
         'Planstand macht es sichtbar – für Fachleute, Behörden, Investoren und künftige Bewohnerinnen und Bewohner.</p>'
         '<h2>Medienmitteilung senden</h2><p>Senden Sie Medienmitteilungen, Bilder (mit Freigabe und Bildnachweis) und Termine an '
         '<b>redaktion@planstand.ch</b>. Wir berichten über Wettbewerbe, Planungsschritte, Baustart, Aufrichte, Vermarktung und Bezug.</p>'
         '<h2>Projekt-Steckbrief</h2><p>Jedes grössere Projekt erhält einen Steckbrief mit Phase, Meilensteinen, Fakten und Links. '
         'In der Beta-Phase tragen wir Projekte kostenlos ein. Senden Sie uns: Projektname, Ort, Bauherrschaft, Architektur, '
         'Nutzung und Anzahl Wohnungen, Zeitplan, Website, ein Bild.</p>'
         '<h2>Was Planstand nicht macht</h2><p>Keine bezahlten Inhalte ohne Kennzeichnung, keine Personendaten privater Bauherrschaften.</p></article>')

    # Projekte
    by_phase = "".join(
        f'<section><h2>{i}. {ph}</h2><div class="grid">{"".join(card(p) for p in projekte if p["phase"] == i)}</div></section>'
        for i, ph in enumerate(PHASEN, 1) if any(p["phase"] == i for p in projekte))
    page("projekte/", "Projekte", "Immobilien- und Arealprojekte in Zug und Zürich nach Phase: Planung, Mitwirkung, "
         "Parlament, Abstimmung, Bewilligung, Bau, Bezug.", f"<h1>Projekte</h1>{by_phase}")

    for p in projekte:
        ms = p.get("meilensteine", [])
        n = next_step(p)
        rows = ""
        for m in ms:
            d = mdate(m.get("datum"))
            st = "next" if m is n else ("done" if d and d < TODAY else "later")
            q = f' <a href="{e(m["quelle"])}" rel="noopener" target="_blank">Quelle</a>' if m.get("quelle") else ""
            rows += f'<li class="{st}"><span>{e(dlabel(m["datum"]))}</span>{e(m["text"])}{q}</li>'
        fakten = "".join(f"<dt>{e(a)}</dt><dd>{e(b)}</dd>" for a, b in p.get("fakten", []))
        links = "".join(f'<li><a href="{e(b)}" rel="noopener" target="_blank">{e(a)}</a></li>' for a, b in p.get("links", []))
        pm = [m for m in meldungen if p["slug"] in m.get("projekte", [])]
        body = (f'<div class="ph{p["phase"]}"><p class="crumb"><a href="{u("kantone/" + p["kanton"].lower() + "/")}">{KT[p["kanton"]]}</a> › <a href="{u("orte/" + p["kslug"] + "/")}">{e(p["gemeinde"])}</a> · {e(p.get("art", ""))}</p>'
                f'<h1>{e(p["titel"])}</h1><p class="lead">{e(p.get("untertitel", ""))}</p>{phasebar(p["phase"])}'
                + (f'<div class="nextbox"><b>Nächster Schritt, {e(dlabel(n["datum"]))}:</b> {e(n["text"])}</div>' if n else "")
                + f'<section class="two"><div><p>{e(p.get("kurz", ""))}</p>'
                + (f'<p class="note"><b>Mitreden:</b> {e(p["mitreden"])}</p>' if p.get("mitreden") else "")
                + f'<h2>Meilensteine</h2><ol class="ms">{rows}</ol>'
                f'<h2>Meldungen</h2>{mlist([m for m in pm if m["typ"] != "Medien"], empty="Noch keine automatisch zugeordneten Meldungen.")}'
                f'<h2>In den Medien</h2>{mlist([m for m in pm if m["typ"] == "Medien"], False, "Noch keine Medienberichte zugeordnet.")}'
                f'</div><aside><dl class="facts">{fakten}</dl><h3>Links</h3><ul class="links">{links}</ul>'
                f'<p class="note">Stand Dossier: {e(dlabel(p.get("stand", "")) or "laufend")}. Fehler oder Ergänzung? '
                f'<a href="{u("projekt-melden/")}">Melden</a></p></aside></section></div>')
        page(f'projekte/{p["slug"]}/', p["titel"], f'{p["titel"]} in {p["gemeinde"]}: Phase {PHASEN[p["phase"] - 1]}, '
             f'nächste Schritte, Meilensteine und Meldungen.', body)

    # Orte
    lst = ""
    for kt in AKTIV:
        items = sorted(((k, o) for k, o in orte.items() if o["kanton"] == kt), key=lambda kv: kv[1]["name"])
        lst += (f'<section><h2>{KT[kt]}</h2><ul class="olist">' + "".join(
            f'<li><a href="{u("orte/" + k + "/")}">{e(o["name"])}</a> <span>{len(o["p"])} Projekte · {len(o["m"])} Meldungen</span></li>'
            for k, o in items) + "</ul></section>")
    ok = "".join(ortkachel(k, o) for k, o in sorted(((k, o) for k, o in orte.items() if o["p"]), key=lambda kv: (-len(kv[1]["p"]), kv[1]["name"])))
    page("orte/", "Orte", "Bauvorhaben und amtliche Meldungen nach Gemeinde in den Kantonen Zug und Zürich.",
         f'<h1>Orte</h1><p class="lead">Orte mit Projekt-Dossiers. Darunter alle Gemeinden mit amtlichen Meldungen.</p><div class="orte">{ok}</div>{lst}')
    for k, o in orte.items():
        tm = sorted(((mdate(n["datum"]), p, n) for p in o["p"] if (n := next_step(p)) and mdate(n["datum"]) and bald(n)), key=lambda t: t[0])
        tm_html = "".join(f'<li><span class="meta">{e(dlabel(n["datum"]))}</span><a href="{u("projekte/" + p["slug"] + "/")}">'
                          f'{e(p["titel"])}</a><span class="d">{e(n["text"])}</span></li>' for _, p, n in tm)
        body = (f'<p class="crumb"><a href="{u("kantone/")}">Schweiz</a> › <a href="{u("kantone/" + o["kanton"].lower() + "/")}">{KT[o["kanton"]]}</a> › {e(o["name"])}</p>'
                + (board(o["p"], f'Bauprojekte in {o["name"]}', f'{len(o["p"])} Projekte von der ersten Planung bis zum Bezug.')
                   if o["p"] else f'<h1>{e(o["name"])}</h1><p class="note">Noch keine Projekt-Steckbriefe. '
                   f'<a href="{u("projekt-melden/")}">Projekt melden</a></p>')
                + (f'<section><h2>Nächste Termine</h2><ul class="mlist">{tm_html}</ul></section>' if tm_html else "")
                + f'<section><div class="shead"><h2>Meldungen</h2><a href="{u("orte/" + k + "/rss.xml")}">RSS</a></div>'
                f'{mlist(o["m"][:80], False)}</section>')
        page(f"orte/{k}/", f'Bauprojekte {o["name"]}', f'Bauprojekte, Baugesuche und Planungen in {o["name"]} '
             f'({KT[o["kanton"]]}): Phase, nächste Schritte, amtliche Meldungen.', body, f"orte/{k}/rss.xml")
        rss(f"orte/{k}/rss.xml", f'{NAME} – {o["name"]}', o["m"])

    # Kantone (Ebene 2): Pipeline, nächste Entscheide, Orte, News
    zeilen = ""
    for kt in sorted(KANTONE, key=lambda k: (k not in AKTIV, KANTONE[k])):
        if kt in AKTIV:
            zeilen += (f'<li><a href="{u("kantone/" + kt.lower() + "/")}">{e(KT[kt])}</a> <span>{sum(1 for p in projekte if p["kanton"] == kt)} Projekte · '
                       f'{sum(1 for o in orte.values() if o["kanton"] == kt)} Gemeinden mit Meldungen</span></li>')
        else:
            zeilen += f'<li class="off">{e(KT[kt])} <span>in Vorbereitung</span></li>'
    kk = "".join(kantkachel(kt, [p for p in projekte if p["kanton"] == kt],
                            sum(1 for o in orte.values() if o["kanton"] == kt and o["p"])) for kt in AKTIV)
    page("kantone/", "Kantone", "Immobilien- und Arealentwicklung nach Kanton: Projekte, Phasen und nächste Entscheide.",
         f'<p class="crumb">Schweiz</p><h1>Kantone</h1><p class="lead">Planstand berichtet national und baut die Datentiefe Kanton um Kanton aus. '
         f'Erfasst sind derzeit {", ".join(KANTONE[k] for k in AKTIV)}.</p><div class="orte">{kk}</div>'
         f'<section><h2>Alle Kantone</h2><ul class="olist">{zeilen}</ul></section>')
    for kt in AKTIV:
        kp = [p for p in projekte if p["kanton"] == kt]
        km = [m for m in meldungen if m.get("kanton") == kt]
        kbg = [m for m in bg30 if m.get("kanton") == kt]
        ktm = sorted(((mdate(n["datum"]), p, n) for p in kp if (n := next_step(p)) and mdate(n["datum"]) and bald(n)), key=lambda t: t[0])
        ktm_html = "".join(f'<li>{dblock(n, i == 0)}<span><a href="{u("projekte/" + p["slug"] + "/")}">{e(p["titel"])}</a>'
                           f'<small>{e(p["gemeinde"])} · {e(n["text"])}</small></span></li>' for i, (_, p, n) in enumerate(ktm[:8]))
        ko = sorted(((k, o) for k, o in orte.items() if o["kanton"] == kt and o["p"]), key=lambda kv: (-len(kv[1]["p"]), kv[1]["name"]))
        body = (f'<p class="crumb"><a href="{u("kantone/")}">Schweiz</a> › {e(KT[kt])}</p>'
                f'<section class="mast"><div class="wm"><h1>{e(KT[kt])}</h1><p>Pipeline der grösseren Immobilien- und Arealprojekte, '
                f'nächste Entscheide und News.</p></div><div class="stats"><div><b>{len(kp)}</b><span>Projekte<br>im Fokus</span></div>'
                f'<div><b>{len(ko)}</b><span>Orte mit<br>Dossiers</span></div><div><b>{sum(wohnungen(m) for m in kbg)}</b>'
                f'<span>Wohnungen<br>beantragt (30 Tage)</span></div></div></section>'
                + (board(kp, "Pipeline", f'{len(kp)} Projekte von der ersten Planung bis zum Bezug.') if kp else
                   '<p class="note">Noch keine Projekt-Steckbriefe.</p>')
                + (f'<section class="termine voll"><h2 class="sh">Nächste Entscheide</h2><ul>{ktm_html}</ul></section>' if ktm_html else "")
                + (f'<section><div class="sh"><h2>Orte</h2><a href="{u("orte/")}">Alle Orte →</a></div><div class="orte">'
                   f'{"".join(ortkachel(k, o) for k, o in ko)}</div></section>' if ko else "")
                + f'<section><div class="sh"><h2>News</h2></div>{mlist([m for m in km if m["typ"] != "Baugesuch"][:40])}</section>')
        page(f"kantone/{kt.lower()}/", f"Immobilienprojekte {KT[kt]}", f"Immobilien- und Arealentwicklung im {KT[kt]}: "
             f"Projekt-Pipeline nach Phase, nächste Entscheide, Orte und News.", body)

    page("meldungen/", "News", "News zur Immobilien- und Arealentwicklung in Zug und Zürich: Medienmitteilungen, Planungen, Medienberichte.",
         f'<h1>News</h1><p class="note">Medienmitteilungen, Planungsentscheide und Medienberichte. Baugesuche finden Sie im '
         f'<a href="{u("baugesuche/")}">Baugesuch-Radar</a>.</p>{mlist([m for m in meldungen if m["typ"] != "Baugesuch"][:300])}')
    page("newsletter/", "Newsletter", "Der Planstand-Wochenbrief: jede Woche die wichtigsten Entwicklungen der Immobilien- und Arealentwicklung in der Schweiz.",
         '<h1>Wochenbrief</h1><p>Jede Woche die fünf wichtigsten Entwicklungen und die Zahlen der Woche aus der Immobilien- '
         'und Arealentwicklung in der Schweiz: Projekte, Entscheide, Termine. Kostenlos.</p><p class="note">Anmeldung folgt in Kürze. '
         f'Bis dahin: <a href="{u("rss.xml")}">RSS-Feed</a>.</p>')
    page("ueber/", "Über", "Was Planstand ist, woher die Daten stammen und wie sie aktualisiert werden.",
         '<h1>Über Planstand</h1><p>Planstand ist ein unabhängiges Online-Medium zur Immobilien- und Arealentwicklung in den '
         'Kantonen Zug und Zürich. Im Zentrum steht eine Projekt-Datenbank: welche Vorhaben es gibt, in welcher Phase sie '
         'sind und was als Nächstes kommt.</p><h2>Quellen</h2><ul><li>Amtsblätter der Kantone Zug und Zürich '
         '(Amtsblattportal des SECO), zweimal täglich</li><li>Medienmitteilungen von Kanton, Gemeinden und Entwicklern</li>'
         '<li>Fachmedien: nur Titel und Link</li></ul><p>Personendaten aus amtlichen Publikationen werden nicht übernommen. '
         'Massgebend sind immer die verlinkten Originalquellen.</p>')

    rss("rss.xml", f"{NAME} – alle Meldungen", meldungen)
    sm = "".join(f"<url><loc>{e(SITE_URL.rstrip('/') + '/' + p)}</loc></url>" for p in PAGES)
    (OUT / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{sm}</urlset>')
    (OUT / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL.rstrip('/')}/sitemap.xml\n")
    print(f"{len(PAGES)} Seiten, {len(orte)} Orte, {len(projekte)} Projekte, {len(meldungen)} Meldungen _site/")


def rss(path: str, title: str, items: list[dict]) -> None:
    it = ""
    for m in items[:50]:
        try:
            pub = format_datetime(datetime.fromisoformat(m["datum"]).replace(tzinfo=timezone.utc))
        except ValueError:
            pub = ""
        it += (f"<item><title>{e(m['titel'])}</title><link>{e(m['url'])}</link><guid isPermaLink=\"false\">{e(m['id'])}</guid>"
               f"<pubDate>{pub}</pubDate><description>{e(' · '.join(x for x in (m['typ'], m.get('gemeinde') or '', m.get('beschrieb') or '') if x))}</description></item>")
    f = OUT / path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>{e(title)}</title>'
                 f'<link>{e(SITE_URL)}</link><description>{e(CLAIM)}</description><language>de-ch</language>{it}</channel></rss>')


if __name__ == "__main__":
    build()
