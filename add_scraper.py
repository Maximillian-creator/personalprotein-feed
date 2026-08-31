"""
Personal Protein ADD-feed
=========================
Volledige productinfo om met Stock Sync NIEUWE producten aan te maken.
Bron: personalprotein.nl (publieke WooCommerce). Zie personalprotein_common.py.

  price       = reguliere prijs (PP_PRIJS_BASIS=actueel geeft de actieprijs)
  barcode     = leeg; Personal Protein voert nergens een EAN/GTIN
  description = eigen tekst + de secties van de configurator-pagina van de ouder
                (Beschrijving, Ingredienten, Voedingswaarden, Gebruik). Producten
                zonder ouder krijgen geen tekst - er wordt niets bijverzonnen.

Elk product heeft precies een variant: WooCommerce kent hier geen varianten, elke
maat/smaak is een eigen SKU. De opties staan wel in de XML zodat Stock Sync ze op
Handle kan groeperen als je dat later wilt.

Zet in Stock Sync de ADD-koppeling op "alleen nieuwe producten aanmaken".
Lokaal: INSECURE_SSL=1, TEST_SKU=<sku>, PP_MERCH=1.
"""

import csv
import re
import time
import xml.etree.ElementTree as ET
from xml.dom import minidom

import personalprotein_common as pc

OUTPUT_FILE = "personalprotein_add_feed.xml"
BRON_FILE = "personalprotein_tekstbron.csv"


def add_child(parent, tag, value):
    el = ET.SubElement(parent, tag)
    el.text = "" if value is None else str(value)
    return el


def build_xml(products):
    root = ET.Element("products")
    for p in products:
        item = ET.SubElement(root, "product")
        add_child(item, "handle", p["handle"])
        add_child(item, "title", p["title"])
        add_child(item, "vendor", p["vendor"])
        add_child(item, "brand", p["brand"])
        add_child(item, "product_type", p["product_type"])
        add_child(item, "tags", p["tags"])
        add_child(item, "published", "false")   # concept-only: publiceren verdien je
        add_child(item, "description", p["description"])
        add_child(item, "body_html", p["description"])
        add_child(item, "bron_url", p["url"])
        add_child(item, "option1_name", "Titel")

        images_el = ET.SubElement(item, "images")
        for src in p["images"]:
            img_el = ET.SubElement(images_el, "image")
            add_child(img_el, "src", src)
        add_child(item, "image_links", ",".join(p["images"]))
        eerste_afbeelding = p["images"][0] if p["images"] else ""

        variants_el = ET.SubElement(item, "variants")
        v_el = ET.SubElement(variants_el, "variant")
        add_child(v_el, "sku", p["sku"])
        add_child(v_el, "barcode", p["barcode"])
        add_child(v_el, "price", f"{p['price']:.2f}")
        add_child(v_el, "compare_at_price", "")
        add_child(v_el, "available", "true" if p["available"] else "false")
        add_child(v_el, "variant_title", p["title"])
        add_child(v_el, "option1", p["title"])
        add_child(v_el, "weight", p["weight"])
        add_child(v_el, "weight_unit", "g")
        add_child(v_el, "image", eerste_afbeelding)
    return root


def schrijf_tekstbron(products, pad=BRON_FILE):
    """Per SKU: waar de tekst vandaan komt en hoeveel het er is.

    Zonder dit bestand is "63 van de 76 hebben een beschrijving" een getal dat je
    moet geloven; hiermee kun je het regel voor regel nakijken.
    """
    with open(pad, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku", "titel", "tekstbron", "woorden", "afbeeldingen",
                    "gewicht_g", "prijs", "prijs_regulier", "prijs_actie",
                    "op_voorraad"])
        for p in products:
            woorden = len(re.sub(r"<[^>]+>", " ", p["description"]).split())
            w.writerow([p["sku"], p["title"],
                        p["tekstbron"] or ("alleen korte omschrijving"
                                           if p["description"] else "GEEN TEKST"),
                        woorden, len(p["images"]), p["weight"],
                        f"{p['price']:.2f}", f"{p['prijs_regulier']:.2f}",
                        f"{p['prijs_actie']:.2f}",
                        "ja" if p["available"] else "nee"])
    print(f"Tekstbron per SKU vastgelegd in {pad}")


def save_xml(root, filepath):
    xml_str = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(xml_str).toprettyxml(indent="  ")
    lines = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines[0] = '<?xml version="1.0" encoding="UTF-8"?>'
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"XML opgeslagen: {filepath}")


def main():
    print("Personal Protein ADD-feed gestart\n")
    start = time.time()
    products = pc.fetch_products(met_teksten=True)
    root = build_xml(products)
    pc.controleer_omvang(len(root.findall("product")), OUTPUT_FILE)
    save_xml(root, OUTPUT_FILE)
    schrijf_tekstbron(products)

    zonder_tekst = [p["sku"] for p in products if not p["description"]]
    zonder_beeld = [p["sku"] for p in products if not p["images"]]
    zonder_gewicht = [p["sku"] for p in products if not p["weight"]]
    print(f"\nKlaar in {time.time() - start:.0f}s - {len(products)} producten")
    print(f"  zonder beschrijving : {len(zonder_tekst)}  {zonder_tekst[:8]}")
    print(f"  zonder afbeelding   : {len(zonder_beeld)}  {zonder_beeld[:8]}")
    print(f"  zonder gewicht      : {len(zonder_gewicht)}  {zonder_gewicht[:8]}")
    print("\nFeed-URL voor Stock Sync (Add products):")
    print("https://raw.githubusercontent.com/Maximillian-creator/"
          "personalprotein-feed/main/personalprotein_add_feed.xml")


if __name__ == "__main__":
    main()
