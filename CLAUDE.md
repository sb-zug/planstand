# Planstand – Hinweise für Claude

Sergio (Inhaber) will so gut wie nichts selbst tun. Änderungen bespricht er im Chat; Claude setzt sie um und pusht direkt auf `main`.
Sprache: Deutsch (Schweiz, «ss» statt «ß»).

## Wochen-Durchlauf (Redaktion)
1. `site/data/meldungen.json` der letzten 7–10 Tage lesen (neu = nicht in projekte zugeordnet).
2. Bestehende Projekte nachführen: Phase, Meilensteine (mit Quelle), nächster Schritt, `keywords` ergänzen.
3. Neue Projekte anlegen, wenn eine Meldung ein grösseres Vorhaben zeigt (Gestaltungs-/Bebauungsplan, Überbauung, Wettbewerb).
   Pflichtfelder: slug, titel, untertitel, art, gemeinde, kanton, phase (1–7), kurz, meilensteine, keywords, links.
4. Texte immer in eigenen Worten, Fakten aus Originalquellen. Keine Medientexte übernehmen, Medien nur verlinken.
5. Medienspiegel: per Websuche Artikel der Fachmedien (Immobilien Business, Hochparterre, espazium, NZZ, Tages-Anzeiger u. a.)
   zu ZG/ZH-Projekten der Woche suchen und in `site/data/medienspiegel.json` eintragen (Titel, Medium, Datum, URL, eigene Notiz).
   Nichts aus dem Artikel abschreiben.
5b. Firmen ohne lesbaren Newsroom (JavaScript oder gesperrt) per Websuche prüfen und relevante Mitteilungen als Medienspiegel-
   oder Projekt-Eintrag aufnehmen: Mobimo, Allreal, Implenia, Steiner, HRS, PSP Swiss Property, Pensimo/Turidomus/Adimora,
   Swiss Life AM, UBS/Zürich Anlagestiftung, Ecoreal, SBB Immobilien, Senn, Walde, Ginesta, Livit, PWG, ABZ, Allgemeine BG Zürich.
   Automatisch beobachtet werden bereits: siehe NEWSROOMS und FEEDS in collector/collect.py (Diagnose: site/data/newsroom_debug.json).
6. Wochenartikel «Die Woche» in `site/data/artikel.json` schreiben (vorne einfügen): Titel mit den 2 wichtigsten Themen, Lead,
   4–6 Absätze mit **fettem** Einstieg, nur Fakten aus Originalquellen (Medienmitteilungen, Amtsblatt, Projektseiten), Quellenliste.
   Planstand ist ein Medium für die Branche (Entwickler, Eigentümer, Vermarkter), kein Baugesuch-Verzeichnis: Projekte und Entscheide vor Baugesuchen.
7. `python3 tests/test_collect.py && python3 collector/build.py` laufen lassen, dann committen und pushen.

## Leitplanken
- Keine Personendaten privater Bauherrschaften publizieren.
- Keine Kundenprojekte von Creafactory ohne ausdrückliche Freigabe von Sergio aufnehmen.
- Nur Python-Standardbibliothek.
