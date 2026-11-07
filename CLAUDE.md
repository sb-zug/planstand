# Planstand – Hinweise für Claude

Sergio (Inhaber) will so gut wie nichts selbst tun. Änderungen bespricht er im Chat; Claude setzt sie um und pusht direkt auf `main`.
Sprache: Deutsch (Schweiz, «ss» statt «ß»).

## Wochen-Durchlauf (Redaktion)
1. `site/data/meldungen.json` der letzten 7–10 Tage lesen (neu = nicht in projekte zugeordnet).
2. Bestehende Projekte nachführen: Phase, Meilensteine (mit Quelle), nächster Schritt, `keywords` ergänzen.
3. Neue Projekte anlegen, wenn eine Meldung ein grösseres Vorhaben zeigt (Gestaltungs-/Bebauungsplan, Überbauung, Wettbewerb).
   Pflichtfelder: slug, titel, untertitel, art, gemeinde, kanton, phase (1–7), kurz, meilensteine, keywords, links.
4. Texte immer in eigenen Worten, Fakten aus Originalquellen. Keine Medientexte übernehmen, Medien nur verlinken.
5. `python3 tests/test_collect.py && python3 collector/build.py` laufen lassen, dann committen und pushen.

## Leitplanken
- Keine Personendaten privater Bauherrschaften publizieren.
- Keine Kundenprojekte von Creafactory ohne ausdrückliche Freigabe von Sergio aufnehmen.
- Nur Python-Standardbibliothek.
