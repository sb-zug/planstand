# Planstand (Arbeitstitel)

Online-Medium für Immobilien- und Arealentwicklung in den Kantonen Zug und Zürich. Kern ist eine Projekt-Datenbank:
welche Vorhaben es gibt, in welcher Phase sie sind (Planung → Mitwirkung → Parlament → Abstimmung → Bewilligung → Bau → Bezug)
und was als Nächstes kommt. Dazu automatisch gesammelte Meldungen nach Ort und ein Wochen-Newsletter (folgt).

Aufbau wie zug.now: statische Seite auf GitHub Pages, Sammler in Python (nur Standardbibliothek), 2× täglich über GitHub Actions.

## Daten

| Datei | Inhalt | Pflege |
|---|---|---|
| `site/data/projekte.json` | Projekt-Steckbriefe mit Phase, Meilensteinen, Stichworten | redaktionell (Claude, Wochen-Durchlauf) |
| `site/data/meldungen.json` | Archiv der gesammelten Meldungen, mit Zuordnung zu Projekten | automatisch |
| `site/data/gesehen.json` | IDs bereits geprüfter, nicht relevanter Publikationen | automatisch |
| `site/data/meta.json` | Status der Quellen beim letzten Lauf | automatisch |

## Quellen

| Quelle | Schnittstelle | Filter |
|---|---|---|
| Amtsblatt ZG | `amtsblatt.zg.ch/api/v1/publications` | Baugesuche grösserer Vorhaben (Volltext), Planungen und Auflagen über Stichworte |
| Amtsblatt ZH | `amtsblatt.zh.ch/api/v1/publications` | wie ZG |
| Hochparterre | RSS | nur Titel + Link |

Personendaten (Testamente, Konkurse, Strafbefehle usw.) werden nie übernommen; bei Baugesuchen wird die Bauherrschaft nicht angezeigt.
Filter-Regeln: `PLUS`, `STRONG`, `SMALL`, `PLANUNG` in `collector/collect.py`.

## Lokal

```
python3 tests/test_collect.py
python3 collector/collect.py            # live (oder --offline tests/fixtures)
python3 collector/build.py              # → _site/
cd _site && python3 -m http.server 8000 # Pfade beginnen mit /planstand/ → BASE_PATH=/ python3 collector/build.py für lokal
```

## Eigene Domain

Settings → Pages → Custom domain (z. B. planstand.ch), beim Anbieter CNAME auf `sb-zug.github.io`.
Dann in `.github/workflows/update.yml` beim Build `SITE_URL=https://planstand.ch` und `BASE_PATH=/` setzen und `site/CNAME` anlegen.
