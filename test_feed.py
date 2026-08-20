"""
Invarianten van de twee feeds
=============================
Geen gedrukt getal zonder een test die zijn betekenis vastpint. Draai deze test
na elke scraper-run:

    python test_feed.py

Hij kijkt niet of de scraper "werkt", maar of de XML betekent wat het etiket
zegt: elke regel een echte SKU, een prijs boven nul, geen dubbelen, en de
optelsom feed + overgeslagen = de hele catalogus.
"""

import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HIER = Path(__file__).parent
UPDATE = HIER / "personalprotein_feed.xml"
ADD = HIER / "personalprotein_add_feed.xml"
OVERGESLAGEN = HIER / "personalprotein_overgeslagen.csv"
BRON = HIER / "personalprotein_tekstbron.csv"

# De catalogus van personalprotein.nl op de dag van bouwen (2026-08-20).
# Wijkt een run hier ver vanaf, dan is er iets veranderd aan de winkel of aan
# de scraper - en dan wil je dat weten voordat Stock Sync ermee aan de haal gaat.
VERWACHT_MINIMAAL = 60
VERWACHT_MAXIMAAL = 120

fouten = []


def eis(voorwaarde, boodschap):
    if not voorwaarde:
        fouten.append(boodschap)


def lees(pad):
    if not pad.exists():
        fouten.append(f"{pad.name} bestaat niet - draai eerst de scraper")
        return None
    return ET.parse(pad).getroot()


def tekst(el, tag):
    kind = el.find(tag)
    return (kind.text or "").strip() if kind is not None else ""


def toets_update():
    root = lees(UPDATE)
    if root is None:
        return []
    regels = root.findall("product")
    eis(regels, "update-feed is leeg")
    skus = []
    for r in regels:
        sku = tekst(r, "sku")
        prijs = tekst(r, "price")
        beschikbaar = tekst(r, "available")
        eis(sku, "regel zonder SKU in de update-feed")
        eis(prijs and float(prijs) > 0, f"{sku}: prijs is '{prijs}' (moet > 0)")
        eis(beschikbaar in ("true", "false"),
            f"{sku}: available is '{beschikbaar}' (moet true of false)")
        skus.append(sku)
    eis(len(skus) == len(set(skus)),
        f"dubbele SKU in de update-feed: "
        f"{sorted({s for s in skus if skus.count(s) > 1})}")
    eis(VERWACHT_MINIMAAL <= len(skus) <= VERWACHT_MAXIMAAL,
        f"update-feed heeft {len(skus)} producten, verwacht tussen "
        f"{VERWACHT_MINIMAAL} en {VERWACHT_MAXIMAAL}")
    return skus


def toets_add(update_skus):
    root = lees(ADD)
    if root is None:
        return
    producten = root.findall("product")
    eis(producten, "add-feed is leeg")
    skus = []
    for p in producten:
        varianten = p.findall("variants/variant")
        eis(len(varianten) == 1,
            f"{tekst(p, 'handle')}: {len(varianten)} varianten (moet er 1 zijn)")
        for v in varianten:
            sku = tekst(v, "sku")
            prijs = tekst(v, "price")
            eis(sku, f"{tekst(p, 'handle')}: variant zonder SKU")
            eis(prijs and float(prijs) > 0, f"{sku}: prijs is '{prijs}' (moet > 0)")
            skus.append(sku)
        eis(tekst(p, "title"), f"{tekst(p, 'handle')}: geen titel")
        eis(tekst(p, "vendor") == "Personal Protein",
            f"{tekst(p, 'handle')}: vendor is '{tekst(p, 'vendor')}'")
        eis(p.findall("images/image"), f"{tekst(p, 'handle')}: geen afbeelding")
        eis(tekst(p, "published") == "false",
            f"{tekst(p, 'handle')}: published moet 'false' zijn (concept-only)")

    eis(len(skus) == len(set(skus)),
        f"dubbele SKU in de add-feed: "
        f"{sorted({s for s in skus if skus.count(s) > 1})}")
    if update_skus:
        eis(set(skus) == set(update_skus),
            "add-feed en update-feed bevatten niet dezelfde SKU's: "
            f"alleen in add {sorted(set(skus) - set(update_skus))[:5]}, "
            f"alleen in update {sorted(set(update_skus) - set(skus))[:5]}")


def toets_verantwoording(aantal_in_feed, met_tekstbron=True):
    """De zeef mag niets stil weglaten."""
    if not OVERGESLAGEN.exists():
        fouten.append("personalprotein_overgeslagen.csv ontbreekt")
        return
    rijen = list(csv.DictReader(OVERGESLAGEN.open(encoding="utf-8")))
    eis(all(r["reden"] for r in rijen),
        "een overgeslagen product zonder reden in de CSV")
    print(f"   {aantal_in_feed} in de feed + {len(rijen)} overgeslagen "
          f"= {aantal_in_feed + len(rijen)} producten verantwoord")

    if met_tekstbron and BRON.exists():
        bron = list(csv.DictReader(BRON.open(encoding="utf-8")))
        eis(len(bron) == aantal_in_feed,
            f"tekstbron-CSV heeft {len(bron)} regels, feed {aantal_in_feed}")
        zonder = [r["sku"] for r in bron if r["tekstbron"] == "GEEN TEKST"]
        print(f"   {len(bron) - len(zonder)} van {len(bron)} met beschrijving, "
              f"{len(zonder)} zonder: {zonder}")


def main():
    """`--alleen-update` slaat de add-feed over.

    De update-feed draait 2x per dag, de add-feed 1x per week. Dan lopen ze een
    week uit de pas en zou een vergelijking tussen beide de dagelijkse run laten
    struikelen op iets wat geen fout is.
    """
    alleen_update = "--alleen-update" in sys.argv
    print("Invarianten van de Personal Protein-feeds\n")
    skus = toets_update()
    if not alleen_update:
        toets_add(skus)
    toets_verantwoording(len(skus), met_tekstbron=not alleen_update)

    if fouten:
        print(f"\n{len(fouten)} probleem/problemen:")
        for f in fouten:
            print(f"  - {f}")
        sys.exit(1)
    print(f"\nAlles klopt: {len(skus)} producten, geen dubbelen, geen prijs 0.")


if __name__ == "__main__":
    main()
