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
CLAIM = "Wo Immobilien- und Arealprojekte in Zug und Zürich stehen"
SITE_URL = os.environ.get("SITE_URL", "https://sb-zug.github.io/planstand")
BASE = os.environ.get("BASE_PATH", "/planstand/")
TODAY = date.today()

PHASEN = ["Planung", "Mitwirkung", "Parlament", "Abstimmung", "Bewilligung", "Bau", "Bezug"]
MON = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sept.", "Okt.", "Nov.", "Dez."]
KT = {"ZG": "Kanton Zug", "ZH": "Kanton Zürich"}

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
    """Meilenstein-Datum → date (Monat/Jahr = Ende) oder None."""
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
<link rel="stylesheet" href="{u('assets/app.css')}">{feed}
<link rel="alternate" type="application/rss+xml" title="{NAME} – alle Meldungen" href="{u('rss.xml')}">
</head><body>
<header class="top"><div class="wrap"><a class="logo" href="{u('')}">{NAME}<span>Beta</span></a>
<nav><a href="{u('projekte/')}">Projekte</a><a href="{u('orte/')}">Orte</a><a href="{u('meldungen/')}">Meldungen</a>
<a href="{u('newsletter/')}" class="nl">Newsletter</a></nav></div></header>
<main class="wrap">{body}</main>
<footer class="foot"><div class="wrap"><p><b>{NAME}</b> sammelt automatisch amtliche Publikationen, Medienmitteilungen und
Projektinformationen zu Immobilien- und Arealentwicklungen in den Kantonen Zug und Zürich. Massgebend sind die verlinkten
Originalquellen. Medienberichte werden nur verlinkt. Prototyp, Stand {dlabel(TODAY.isoformat())}.</p>
<p><a href="{u('rss.xml')}">RSS</a> · <a href="{u('ueber/')}">Über Planstand</a></p></div></footer>
</body></html>"""
    f = OUT / path.lstrip("/")
    if path.endswith("/") or path == "":
        f = f / "index.html"
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(doc)
    PAGES.append(path)


PAGES: list[str] = []


def phasebar(ph: int) -> str:
    cells = "".join(f'<li class="{"done" if i < ph else "now" if i == ph else ""}">{p}</li>'
                    for i, p in enumerate(PHASEN, 1))
    return f'<ol class="phases" aria-label="Phase {ph} von 7: {PHASEN[ph - 1]}">{cells}</ol>'


def next_step(p: dict):
    for m in p.get("meilensteine", []):
        d = mdate(m.get("datum"))
        if d is None or d >= TODAY:
            return m
    return None


def card(p: dict) -> str:
    n = next_step(p)
    nxt = f'<p class="next"><b>Nächster Schritt:</b> {e(dlabel(n["datum"]))} · {e(n["text"])}</p>' if n else ""
    return (f'<a class="card" href="{u("projekte/" + p["slug"] + "/")}"><span class="tag">{e(p["gemeinde"])} · '
            f'{e(PHASEN[p["phase"] - 1])}</span><h3>{e(p["titel"])}</h3><p>{e(p.get("untertitel", ""))}</p>{nxt}</a>')


def mrow(m: dict, ort=True) -> str:
    where = f' · {e(m["gemeinde"])}' if ort and m.get("gemeinde") else ""
    desc = f'<span class="d">{e(m["beschrieb"])}</span>' if m.get("beschrieb") else ""
    return (f'<li><span class="meta">{e(dlabel(m["datum"]))} · {e(m["typ"])}{where} · {e(m["quelle"])}</span>'
            f'<a href="{e(m["url"])}" rel="noopener" target="_blank">{e(m["titel"])}</a>{desc}</li>')


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

    # Start
    top_orte = sorted(orte.items(), key=lambda kv: -(len(kv[1]["p"]) * 5 + len(kv[1]["m"])))[:12]
    chips = "".join(f'<a href="{u("orte/" + k + "/")}">{e(o["name"])}</a>' for k, o in top_orte)
    body = (f'<section class="hero"><h1>{CLAIM}</h1><p>Planstand verfolgt Bauvorhaben von der ersten Planung bis zum Bezug: '
            f'Gestaltungspläne, Mitwirkungen, Abstimmungen, Baugesuche. Automatisch aktualisiert, nach Ort und Projekt geordnet.</p>'
            f'<a class="btn" href="{u("newsletter/")}">Wochen-Newsletter abonnieren</a></section>'
            f'<section><div class="shead"><h2>Projekte</h2><a href="{u("projekte/")}">Alle {len(projekte)} →</a></div>'
            f'<div class="grid">{"".join(card(p) for p in aktiv[:6])}</div></section>'
            f'<section class="two"><div><div class="shead"><h2>Neu im Amtsblatt</h2><a href="{u("meldungen/")}">Alle →</a></div>'
            f'{mlist(amtlich[:12])}</div><div><div class="shead"><h2>In den Fachmedien</h2></div>'
            f'{mlist(medien[:8], empty="Folgt in Kürze.")}<div class="shead"><h2>Orte</h2><a href="{u("orte/")}">Alle →</a></div>'
            f'<p class="chips">{chips}</p>'
            f'</div></section>')
    page("", NAME, f"{CLAIM}: Projekt-Datenbank mit Phase und nächstem Schritt, amtliche Meldungen nach Ort, Wochen-Newsletter.",
         body, "rss.xml")

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
        body = (f'<p class="crumb"><a href="{u("orte/" + p["kslug"] + "/")}">{e(p["gemeinde"])}</a> · {e(p.get("art", ""))}</p>'
                f'<h1>{e(p["titel"])}</h1><p class="lead">{e(p.get("untertitel", ""))}</p>{phasebar(p["phase"])}'
                + (f'<div class="nextbox"><b>Nächster Schritt</b> {e(dlabel(n["datum"]))}: {e(n["text"])}</div>' if n else "")
                + f'<section class="two"><div><p>{e(p.get("kurz", ""))}</p>'
                + (f'<p class="note"><b>Mitreden:</b> {e(p["mitreden"])}</p>' if p.get("mitreden") else "")
                + f'<h2>Meilensteine</h2><ol class="ms">{rows}</ol>'
                f'<h2>Meldungen</h2>{mlist([m for m in pm if m["typ"] != "Medien"], empty="Noch keine automatisch zugeordneten Meldungen.")}'
                f'<h2>In den Medien</h2>{mlist([m for m in pm if m["typ"] == "Medien"], False, "Noch keine Medienberichte zugeordnet.")}'
                f'</div><aside><dl class="facts">{fakten}</dl><h3>Links</h3><ul class="links">{links}</ul>'
                f'<p class="note">Stand Dossier: {e(dlabel(p.get("stand", "")) or "laufend")}. Fehler oder Ergänzung? '
                f'<a href="{u("ueber/")}">Melden</a></p></aside></section>')
        page(f'projekte/{p["slug"]}/', p["titel"], f'{p["titel"]} in {p["gemeinde"]}: Phase {PHASEN[p["phase"] - 1]}, '
             f'nächste Schritte, Meilensteine und Meldungen.', body)

    # Orte
    lst = ""
    for kt in ("ZG", "ZH"):
        items = sorted(((k, o) for k, o in orte.items() if o["kanton"] == kt), key=lambda kv: kv[1]["name"])
        lst += (f'<section><h2>{KT[kt]}</h2><ul class="olist">' + "".join(
            f'<li><a href="{u("orte/" + k + "/")}">{e(o["name"])}</a> <span>{len(o["p"])} Projekte · {len(o["m"])} Meldungen</span></li>'
            for k, o in items) + "</ul></section>")
    page("orte/", "Orte", "Bauvorhaben und amtliche Meldungen nach Gemeinde in den Kantonen Zug und Zürich.", f"<h1>Orte</h1>{lst}")
    for k, o in orte.items():
        body = (f'<p class="crumb">{KT[o["kanton"]]}</p><h1>{e(o["name"])}</h1>'
                f'<section><h2>Projekte</h2>' + (f'<div class="grid">{"".join(card(p) for p in o["p"])}</div>' if o["p"]
                                                 else '<p class="note">Noch keine Projekt-Steckbriefe.</p>')
                + f'</section><section><div class="shead"><h2>Meldungen</h2><a href="{u("orte/" + k + "/rss.xml")}">RSS</a></div>'
                f'{mlist(o["m"][:80], False)}</section>')
        page(f"orte/{k}/", f'Bauprojekte {o["name"]}', f'Bauprojekte, Baugesuche und Planungen in {o["name"]} '
             f'({KT[o["kanton"]]}): Phase, nächste Schritte, amtliche Meldungen.', body, f"orte/{k}/rss.xml")
        rss(f"orte/{k}/rss.xml", f'{NAME} – {o["name"]}', o["m"])

    page("meldungen/", "Meldungen", "Neue amtliche Meldungen zu Bauvorhaben und Planungen in Zug und Zürich.",
         f'<h1>Meldungen</h1><p class="note">Baugesuche grösserer Vorhaben, Gestaltungs- und Bebauungspläne, Auflagen und '
         f'Abstimmungen. Kleinere Baugesuche (z. B. Wärmepumpen) werden ausgefiltert.</p>{mlist(meldungen[:300])}')
    page("newsletter/", "Newsletter", "Der Planstand-Newsletter: jede Woche die wichtigsten Schritte bei Bauvorhaben in Zug und Zürich.",
         '<h1>Wochen-Newsletter</h1><p>Jede Woche die wichtigsten Schritte bei Immobilien- und Arealprojekten in Zug und Zürich: '
         'neue Projekte, Auflagen, Abstimmungen, Baugesuche. Kostenlos.</p><p class="note">Anmeldung folgt in Kürze. '
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
    print(f"{len(PAGES)} Seiten, {len(orte)} Orte, {len(projekte)} Projekte, {len(meldungen)} Meldungen → _site/")


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
