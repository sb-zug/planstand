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
assert not C.relevant("BP", "x", "Neubau Wegbeleuchtung")
assert not C.relevant("BP", "x", "Abbruch EFH / Neubau MFH")
assert not C.relevant("BP", "x", "Liftanbau Mehrfamilienhaus, Wohn- und Gewerbezone")
assert not C.relevant("BP", "x", "4. Projektänderung zu dem bewilligten Ersatzneubau Mehrfamilienhaus mit 12 Wohnungen")
assert C.relevant("BP", "x", "Ersatzneubau mit 7 Wohnhäusern und Tiefgarage für 75 Autos")
assert C.relevant("BP", "x", "Ersatzneubau 2 Mehrfamilienhäuser mit 26 Wohnungen und gemeinsamer Tiefgarage")
assert C.relevant("BP", "x", "Neubau Wohn- und Geschäftshaus mit Tiefgarage")
assert C.relevant("BP", "x", "Ersatzneubau Mehrfamilienhaus mit 13 Wohnungen")
assert not C.relevant("BP", "x", "Ersatzneubau Mehrfamilienhaus mit 5 Wohnungen")
# Planung
assert C.relevant("KO", "Öffentliche Auflage: Bebauungsplan Lorzenallmend, Zug")
assert not C.relevant("KO", "Öffentliche Auflage: Totalrevision Abwasserreglement (AR) der Einwohnergemeinde Baar, Baar")
assert not C.relevant("BP", "Testamentseröffnung: X", "Neubau Mehrfamilienhaus")
assert C.relevant("RP", "Privater Gestaltungsplan «Wasen-Maiacher» Öffentliche Auflage, Boppelsen")
assert not C.relevant("VE", "Strassenlärmsanierung: Rautistrasse, Öffentliche Planauflage, Zürich")
assert not C.relevant("RP", "Festlegung der Gewässerräume im Siedlungsgebiet Walchwil, Öffentliche Auflage")
assert C.relevant("RP", "Kommunale Nutzungsplanung. Privater Gestaltungsplan „Alte Landstrasse, Obermeilen“")
assert not C.relevant("BP", "x", "Ersatz eines Reklameträgers, im Perimeter des Bebauungsplans")
assert not C.relevant("BP", "x", "Luft/Wasser-Wärmepumpe auf dem Dach, Siedlung Heuried")
# Feed mit HTML-Entities
f = C.parse_feed('<rss><channel><item><title>Wohnen &nbsp;am See & mehr</title><link>https://x.ch/a</link>'
                 '<pubDate>Fri, 06 Nov 2026 10:00:00 +0100</pubDate></item></channel></rss>', "T")
assert f and f[0]["datum"] == "2026-11-06" and "am See" in f[0]["titel"]
f = C.parse_feed('<rss><channel><item><title><![CDATA[Neubau <b>am See]]></title><link>https://x.ch/b</link>'
                 '<description>kaputt < 5 & <br></description></item></channel></rss>', "T")
assert f and f[0]["url"] == "https://x.ch/b"
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
