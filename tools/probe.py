#!/usr/bin/env python3
"""Quellen-Test: prüft Kandidaten-URLs (Feed direkt oder Feed-Erkennung auf HTML-Seiten) und robots.txt.
Läuft in GitHub Actions (Workflow «Quellen testen»), Ergebnis → tools/probe_result.json.
"""
import json
import re
import sys
import urllib.parse
import urllib.request
import urllib.robotparser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collector"))
import collect as C  # noqa: E402

HERE = Path(__file__).resolve().parent
CANDS = json.loads((HERE / "probe_candidates.json").read_text())


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": C.UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read(800_000).decode("utf-8", "replace")


def robots_ok(url):
    p = urllib.parse.urlsplit(url)
    rp = urllib.robotparser.RobotFileParser(f"{p.scheme}://{p.netloc}/robots.txt")
    try:
        rp.read()
        return rp.can_fetch(C.UA, url) and rp.can_fetch("*", url)
    except Exception:  # noqa: BLE001
        return None


def try_feed(url, body):
    if "<rss" in body[:3000] or "<feed" in body[:3000] or "<rdf:RDF" in body[:3000]:
        items = C.parse_feed(body, "probe")
        return {"feed": url, "items": len(items), "latest": items[0]["datum"] if items else None,
                "sample": [i["titel"][:90] for i in items[:3]]}
    return None


def probe(name, url):
    res = {"name": name, "url": url}
    try:
        st, ct, body = get(url)
        res["status"] = st
        f = try_feed(url, body)
        if f:
            res.update(f)
        else:
            links = re.findall(r'<link[^>]+type="application/(?:rss|atom)\+xml"[^>]*>', body, re.I)
            hrefs = [urllib.parse.urljoin(url, h) for l in links for h in re.findall(r'href="([^"]+)"', l)]
            hrefs += [urllib.parse.urljoin(url, h) for h in re.findall(r'href="([^"]*(?:rss|feed)[^"]*)"', body, re.I)][:6]
            res["html"] = True
            host = urllib.parse.urlsplit(url).netloc
            nl = []
            for h, t in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', body, re.S | re.I):
                full = urllib.parse.urljoin(url, h)
                txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()
                if urllib.parse.urlsplit(full).netloc == host and len(txt) > 30 and \
                        re.search(r"news|medien|media|press|aktuell|mitteilung|insights|blog", full, re.I) and full.rstrip("/") != url.rstrip("/"):
                    nl.append((full, txt[:90]))
            nl = list(dict.fromkeys(nl))
            res["newslinks"] = len(nl)
            res["newssample"] = [t for _, t in nl[:3]]
            res["links"] = list(dict.fromkeys(hrefs))[:8]
            res["title"] = (re.search(r"<title[^>]*>(.*?)</title>", body, re.S | re.I) or [None, ""])[1].strip()[:80]
            for h in dict.fromkeys(hrefs):
                try:
                    _, _, b2 = get(h)
                    f = try_feed(h, b2)
                    if f and f["items"]:
                        res.update(f)
                        break
                except Exception as e:  # noqa: BLE001
                    res.setdefault("feed_errors", []).append(f"{h}: {e}"[:120])
    except Exception as e:  # noqa: BLE001
        res["error"] = str(e)[:160]
    res["robots_ok"] = robots_ok(res.get("feed") or url)
    return res


NEWSWORD = re.compile(r"^(news|medien|media|newsroom|medienmitteilungen|aktuell|aktuelles|presse|press|mitteilungen|neuigkeiten)$", re.I)


def find_newsroom(url):
    """Auf der Startseite den Link «News/Medien/Aktuell» suchen."""
    try:
        _, _, body = get(url)
    except Exception:  # noqa: BLE001
        return None
    for h, t in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', body, re.S | re.I):
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t)).strip()
        if NEWSWORD.match(txt):
            return urllib.parse.urljoin(url, h)
    return None


out = []
for group, items in CANDS.items():
    for name, url in items:
        nr = find_newsroom(url) if group.startswith("Startseiten") else None
        r = probe(name, nr or url)
        r["newsroom_found"] = nr
        r["group"] = group
        print(json.dumps(r, ensure_ascii=False)[:300])
        out.append(r)
(HERE / "probe_result.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
