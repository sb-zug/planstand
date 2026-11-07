"""Schnelltests für Filter und Zuordnung:  python3 tests/test_collect.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collector"))
import collect as C  # noqa: E402

# Filter Baugesuche
assert C.relevant("BP", "Bahnhofstrasse 1, Baar", "Neubau Mehrfamilienhaus mit 24 Wohnungen und Tiefgarage")
assert C.relevant("BP", "Feldweg 3, Cham", "Arealüberbauung Feldpark, Gestaltungsplan Nr. 7")
assert not C.relevant("BP", "Obermattli 1, Walchwil", "Ersatz Ölheizung durch Wärmepumpe")
assert not C.relevant("BP", "Rainweg 2, Zug", "Neubau Einfamilienhaus mit Photovoltaikanlage")
assert not C.relevant("BP", "Rainweg 2, Zug", "")
# Planung
assert C.relevant("KO", "Öffentliche Auflage: Bebauungsplan Lorzenallmend, Zug")
assert not C.relevant("KO", "Öffentliche Auflage: Totalrevision Abwasserreglement (AR) der Einwohnergemeinde Baar, Baar")
assert not C.relevant("BP", "Testamentseröffnung: X", "Neubau Mehrfamilienhaus")
# Gemeinde
assert C.gemeinde("ZG", "Gemeinde Steinhausen - Präsidiales", "x") == "Steinhausen"
assert C.gemeinde("ZG", "Kanton Zug", "Kommunale Baugesuchspublikation: Obermattli 1, Walchwil") == "Walchwil"
assert C.gemeinde("ZH", "Stadt Winterthur - Baupolizeiamt", "x") == "Winterthur"
assert C.gemeinde("ZH", "Kanton Zürich", "Baugesuch Seestrasse 5, 8800 Thalwil") == "Thalwil"
# XML
full, desc = C.xml_text("<a><projectDescription>Neubau Wohnüberbauung mit 80 Wohnungen</projectDescription></a>")
assert "80 Wohnungen" in desc and C.relevant("BP", "x", full)
# Zuordnung
items = [{"titel": "Bebauungsplan LG-Areal: Auflage", "beschrieb": "", "gemeinde": "Zug", "typ": "Raumplanung"}]
C.match_projects(items, [{"slug": "lg-areal", "gemeinde": "Zug", "keywords": ["lg-areal"]}])
assert items[0]["projekte"] == ["lg-areal"]
print("ok")
