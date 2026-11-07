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
# Medienmitteilungen / Medien
raw = [{"titel": "Neue Überbauung mit 120 Wohnungen in Baar", "beschrieb": "Die Firma X baut. " * 30, "url": "https://a.ch/1", "datum": "2026-11-06"},
       {"titel": "Auto Zürich 2026: Premieren", "beschrieb": "Autos", "url": "https://a.ch/2", "datum": "2026-11-06"},
       {"titel": "Wohnungen in Bern", "beschrieb": "", "url": "https://a.ch/3", "datum": "2026-11-06"}]
mm = C.mm_items(raw, "presseportal.ch", None, None, True)
assert len(mm) == 1 and mm[0]["gemeinde"] == "Baar" and mm[0]["kanton"] == "ZG" and len(mm[0]["beschrieb"]) <= 262
md = C.mm_items(raw, "zentralplus", None, None, True, "medien")
assert md[0]["typ"] == "Medien" and md[0]["beschrieb"] == ""
# Newsroom
body = ('<a href="/de/news">News</a><a href="/de/news/2026/neubau-wohnueberbauung-in-cham">Publiziert am 16.10.2026 Halter baut 120 Wohnungen in Cham</a>'
        '<a href="https://other.ch/news/x">Ein externer Link mit sehr langem Text hier</a>')
h = C.harvest("https://www.halter.ch/de/news", body)
assert len(h) == 1 and h[0][0].endswith("cham"), h
assert C._datum("", "Publiziert am 16.10.2026 Halter") == "2026-10-16"
page = '<meta property="og:title" content="Halter baut 120 Wohnungen in Cham | Halter"><meta property="og:description" content="Überbauung mit 120 Wohnungen in Cham.">'
it = C.newsroom_item("Halter", None, None, h[0][0], h[0][1], page)
assert it["titel"] == "Halter baut 120 Wohnungen in Cham" and it["datum"] == "2026-10-16"
assert C.mm_items([it], "Halter", None, None, True)[0]["gemeinde"] == "Cham"
assert C._datum('<script>var x="1.1.2020"</script><p>Zug, 3. November 2026</p>') == "2026-11-03"
assert C._datum('{"datePublished": "2026-10-01T08:00"}') == "2026-10-01"
assert C._datum('<time datetime="2026-09-12">') == "2026-09-12"
assert C.harvest("https://www.halter.ch/de/news", '<a href="/fr/news/x-y">Dépôt dune demande de permis de construire très long</a>') == []
x = C.newsroom_einordnen({"titel": "Avadis Anlagestiftung übernimmt Immobilienportfolio", "beschrieb": "", "url": "https://a.ch/n/1", "datum": "2026-10-01"}, "Avadis", None, None)
assert x and x["typ"] == "Branche"
x = C.newsroom_einordnen({"titel": "Zuger Immobilienmarkt: starke Nachfrage", "beschrieb": "", "url": "https://a.ch/n/2", "datum": "2026-10-01"}, "Zuger Kantonalbank", "ZG", None)
assert x and x["kanton"] == "ZG"
assert C.newsroom_einordnen({"titel": "Die Sommerfeste von Losinger Marazzi AG", "beschrieb": "", "url": "u", "datum": "d"}, "L", None, None) is None
assert C.newsroom_einordnen({"titel": "Pierre de Soleil: Rohbauarbeiten in Lucens gestartet", "beschrieb": "", "url": "u", "datum": "d"}, "L", None, None) is None
assert C.newsroom_einordnen({"titel": "Baueingabe für die Wiedereröffnung der Buvette Sonnenberg in Seelisberg Schlieren / Seelisberg 30.10.2026", "beschrieb": "Halter AG, Schlieren", "url": "u", "datum": "d"}, "Halter", None, None) is None
assert C.newsroom_einordnen({"titel": "Dépôt d’une demande de permis de construire", "beschrieb": "", "url": "u", "datum": "d"}, "Halter", None, None) is None
x = C.newsroom_einordnen({"titel": "Patrimonium Anlagestiftung erreicht CHF 1.8 Mrd. Anlagevermögen", "beschrieb": "Baar, 27.10.2026", "url": "u", "datum": "d"}, "Patrimonium", None, None)
assert x and x["typ"] == "Branche" and x["gemeinde"] is None
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
