"""
Personal Protein UPDATE-feed
============================
Lichte feed om BESTAANDE producten bij te werken: verkoopprijs + beschikbaarheid.
Matcht in Stock Sync op **SKU** (Personal Protein voert geen EAN, dus barcode
blijft leeg).

  price     = reguliere prijs (PP_PRIJS_BASIS=actueel geeft de actieprijs)
  available = in/uit voorraad bij Personal Protein (geen aantal beschikbaar)

Bron: personalprotein.nl (publieke WooCommerce Store API). Zie
personalprotein_common.py. Lokaal: INSECURE_SSL=1, TEST_SKU=<sku>.
"""

import time
import xml.etree.ElementTree as ET
from xml.dom import minidom

import personalprotein_common as pc

OUTPUT_FILE = "personalprotein_feed.xml"


def build_xml(products):
    root = ET.Element("products")
    for p in products:
        item = ET.SubElement(root, "product")

        def add(tag, value):
            el = ET.SubElement(item, tag)
            el.text = "" if value is None else str(value)

        add("sku", p["sku"])
        add("barcode", p["barcode"])
        add("title", p["title"])
        add("price", f"{p['price']:.2f}")
        add("compare_at_price", "")
        add("available", "true" if p["available"] else "false")
        add("handle", p["handle"])
    return root


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
    print("Personal Protein UPDATE-feed gestart\n")
    start = time.time()
    products = pc.fetch_products(met_teksten=False)
    root = build_xml(products)
    pc.controleer_omvang(len(root.findall("product")), OUTPUT_FILE)
    save_xml(root, OUTPUT_FILE)
    print(f"Klaar in {time.time() - start:.0f}s - {len(products)} producten")
    print("\nFeed-URL voor Stock Sync (Update):")
    print("https://raw.githubusercontent.com/Maximillian-creator/"
          "personalprotein-feed/main/personalprotein_feed.xml")


if __name__ == "__main__":
    main()
