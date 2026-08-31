"""
Personal Protein — gedeelde kern
================================
personalprotein.nl is een publieke **WooCommerce**-winkel (WordPress, geen login).
Alles komt uit twee bronnen:

  1. /wp-json/wc/store/v1/products  -> de hele catalogus: sku, prijs (regulier en
                                      actie), voorraad, afbeeldingen, categorieen,
                                      tags, korte + lange beschrijving.
  2. de configurator-pagina's       -> de uitklapsecties (Beschrijving,
                                      Ingredienten, Voedingswaarden, Gebruik) en
                                      `data-options_data` = welke SKU's eronder hangen.

Bijzonderheden van deze winkel — waarom de code doet wat hij doet:

- De catalogus bestaat uit **82 `simple`-producten** (de echte, verkoopbare SKU's)
  en **31 `composite`/`bundle`-producten** (configurators: "kies je maat + 2 gratis
  flavour shots"). De configurators geven in de Store API **prijs "0"** terug.
  Ze gaan daarom NIET de feed in; ze dienen alleen als tekstbron.
- De losse SKU-pagina's zijn niet publiek (301 -> /winkel/). De productteksten staan
  dus uitsluitend op de configurator-pagina van de ouder.
- **Nergens een EAN/GTIN** — niet in de API, niet in schema.org, niet in de HTML.
  `barcode` blijft dus leeg; Stock Sync matcht op **SKU**.
- Voorraad is alleen in/uit (`is_in_stock`), geen aantal.

Prijsbeleid (env `PP_PRIJS_BASIS`):
  "advies"  = de reguliere prijs zonder actie  (STANDAARD)
  "actueel" = de vandaag getoonde prijs, inclusief lopende actie
Optioneel `PP_PRIJS_FACTOR` (bv. 1.05) vermenigvuldigt de prijs. Standaard 1.0.
Er wordt nooit een compare_at_price verzonnen: die blijft leeg.

Lokaal testen achter een SSL-onderscheppende proxy: INSECURE_SSL=1.
Een product testen: TEST_SKU=<sku>.  Merch meenemen: PP_MERCH=1.
"""

import csv
import json
import os
import re
import time
from html import unescape

import requests

BASE_URL = "https://www.personalprotein.nl"
STORE_API = f"{BASE_URL}/wp-json/wc/store/v1/products"
BRAND = "Personal Protein"
REQUEST_DELAY = 0.5
OVERGESLAGEN_FILE = "personalprotein_overgeslagen.csv"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; GFY-PersonalProteinFeed/1.0)",
    "Accept-Language": "nl-NL,nl;q=0.9",
}

VERIFY_SSL = os.environ.get("INSECURE_SSL") != "1"
if not VERIFY_SSL:
    import urllib3
    urllib3.disable_warnings()

PRIJS_BASIS = os.environ.get("PP_PRIJS_BASIS", "advies").lower()
PRIJS_FACTOR = float(os.environ.get("PP_PRIJS_FACTOR", "1.0"))
MERCH_MEE = os.environ.get("PP_MERCH") == "1"

# Categorieen die geen supplement/voeding zijn. Met PP_MERCH=1 gaan ze wel mee.
MERCH_CATEGORIEEN = {"kleding en accessoires", "extra's", "accessoires"}

# Secties op de configurator-pagina die over Personal Protein zelf gaan en dus
# niet mee mogen in onze eigen productteksten.
SECTIE_NIET_OVERNEMEN = {"support", "reviews", "verzending", "retour"}

# Categorieen die reclame zijn, geen soort product. "Bestseller" is geen
# producttype; "Eiwitshakes" wel.
GEEN_PRODUCTTYPE = {"bestseller", "summer sale", "sale", "aanbieding", "nieuw",
                    "uitverkoop", "packs", "extra's"}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _cache_pad(url):
    """Alleen voor lokaal ontwikkelen: PP_CACHE_DIR=... zet opgehaalde pagina's
    op schijf, zodat je de tekstverwerking kunt bijschaven zonder de winkel van
    Personal Protein 70 keer opnieuw te bevragen."""
    map_ = os.environ.get("PP_CACHE_DIR")
    if not map_ or "wp-json" in url:      # de API nooit uit cache: die moet vers
        return None
    os.makedirs(map_, exist_ok=True)
    naam = re.sub(r"[^a-zA-Z0-9]+", "_", url)[-120:] + ".html"
    return os.path.join(map_, naam)


def _get(url, retries=3):
    pad = _cache_pad(url)
    if pad and os.path.exists(pad):
        class _Cached:
            text = open(pad, encoding="utf-8", errors="replace").read()

            def json(self):
                import json as _j
                return _j.loads(self.text)
            headers = {}
        return _Cached()

    for poging in range(retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30, verify=VERIFY_SSL)
            resp.raise_for_status()
            if pad:
                with open(pad, "w", encoding="utf-8") as f:
                    f.write(resp.text)
            return resp
        except Exception as e:
            if poging < retries - 1:
                wacht = (poging + 1) * 15
                print(f"    !  Fout ({e}), opnieuw in {wacht}s...")
                time.sleep(wacht)
            else:
                raise


def fetch_catalogus():
    """Alle producten uit de Store API (alle types, ongefilterd)."""
    producten, pagina = [], 1
    while True:
        resp = _get(f"{STORE_API}?per_page=100&page={pagina}")
        batch = resp.json()
        if not batch:
            break
        producten.extend(batch)
        totaal_paginas = int(resp.headers.get("x-wp-totalpages", pagina))
        if pagina >= totaal_paginas:
            break
        pagina += 1
        time.sleep(REQUEST_DELAY)
    return producten


# --------------------------------------------------------------------------- #
# Configurator-pagina's: componenten + uitklapsecties
# --------------------------------------------------------------------------- #
_DIV_TAG = re.compile(r"</?div\b", re.I)
_COMPONENT = re.compile(
    r'id="component_options_(\d+)"[^>]*data-options_data="(.*?)"', re.S)
_COMPOSITE_SETTINGS = re.compile(r'data-composite_settings="(.*?)"', re.S)
_KOP = re.compile(r'<span class="tw-text-xl[^"]*"[^>]*>(.*?)</span>', re.S)
_PROSE = re.compile(r'<div class="tw-prose[^"]*"[^>]*id="disclosure-\d+"[^>]*>', re.S)


def _balanced_div(src, start):
    """Inhoud van het <div> dat op positie `start` opent, met genest tellen."""
    diepte = 0
    open_eind = src.index(">", start) + 1
    for m in _DIV_TAG.finditer(src, start):
        if m.group(0).lower().startswith("</"):
            diepte -= 1
            if diepte == 0:
                return src[open_eind:m.start()]
        else:
            diepte += 1
    return ""


def _plat(html):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html or ""))).strip()


def parse_configurator(html):
    """(inhoud_ids, secties) van een configurator-pagina.

    Een configurator heeft genummerde onderdelen met een eigen slug: `inhoud` (of
    `eiwitshake`) is wat je koopt, `gratis-flavour-shot` / `1e-flavour-shot` zijn
    de smaakjes die er gratis bij horen. Alleen het eerste soort telt mee, anders
    zou elke flavour shot "onderdeel" zijn van elk eiwitpoeder.

    De id's komen uit `data-options_data`; zoeken op een kaal product-id in de
    HTML zou ook "anderen kochten ook" en "gerelateerde producten" meepakken.
    secties = [(kop, html-inhoud), ...] uit de uitklappers.
    """
    m = _COMPOSITE_SETTINGS.search(html)
    slugs = {}
    if m:
        try:
            slugs = json.loads(unescape(m.group(1))).get("slugs", {})
        except ValueError:
            slugs = {}

    ids = set()
    for comp_id, ruw in _COMPONENT.findall(html):
        if "shot" in (slugs.get(comp_id) or "").lower():
            continue
        for oid in re.findall(r'option_id"\s*:\s*"(\d+)"', unescape(ruw)):
            ids.add(int(oid))

    koppen = [(m.start(), _plat(m.group(1))) for m in _KOP.finditer(html)]
    secties = []
    for m in _PROSE.finditer(html):
        eerder = [t for pos, t in koppen if pos < m.start()]
        kop = eerder[-1] if eerder else ""
        if kop.lower() in SECTIE_NIET_OVERNEMEN:
            continue
        inhoud = _balanced_div(html, m.start()).strip()
        if kop and inhoud:
            secties.append((kop, inhoud))
    return ids, secties


def fetch_configurators(configurators):
    """{id: {'naam','component_ids','secties','categorie','images','tags','short'}}"""
    uit = {}
    for i, c in enumerate(configurators, 1):
        try:
            html = _get(c["permalink"]).text
        except Exception as e:
            print(f"    !  Configurator-pagina faalt bij {c['slug']}: {e}")
            continue
        ids, secties = parse_configurator(html)
        uit[c["id"]] = {
            "naam": c["name"],
            "component_ids": ids,
            "secties": secties,
            "categorieen": [k["name"] for k in c.get("categories", [])],
            "tags": [t["name"] for t in c.get("tags", [])],
            "images": [img["src"] for img in c.get("images", []) if img.get("src")],
            "short": c.get("short_description", "") or "",
        }
        print(f"  [{i}/{len(configurators)}] {c['name'][:42]:<42} "
              f"- {len(ids)} onderdelen, {len(secties)} secties")
        time.sleep(REQUEST_DELAY)
    return uit


# Een configurator met hooguit zoveel inhoud-onderdelen is een echte
# productpagina ("Creatine Monohydraat" = 250 g + 500 g). "Build Your Pack" heeft
# er negen en is dus geen productpagina van een van die negen.
KLEINE_CONFIGURATOR = 3


def kies_ouder(product, configs):
    """De configurator waar dit product de inhoud van is, of None.

    Een product hangt vaak onder meerdere configurators: onder zijn eigen
    productpagina en onder "Build Your Pack" of een try-out pack. Twee routes,
    in deze volgorde:

      1. Naamroute - de productnaam begint met de naam van de configurator
         ("Pure Whey Isolate 1KG" onder "Pure Whey Isolate").
      2. Smalste-ouder-route - de configurator met de minste inhoud-onderdelen,
         als die er hooguit drie heeft en er geen gelijkspel is
         ("Vegan Soy Protein 1kg" onder "Soja Eiwit", niet onder "Build Your Pack").

    Lukt geen van beide, dan liever geen tekst dan de tekst van een ander product.
    """
    onder = [c for c in configs.values() if product["id"] in c["component_ids"]]
    if not onder:
        return None

    naam = product["name"].lower()
    op_naam = [(len(c["naam"]), c["naam"], c) for c in onder
               if naam.startswith(c["naam"].lower())]
    if op_naam:
        return max(op_naam)[2]

    kleinste = min(len(c["component_ids"]) for c in onder)
    smalste = [c for c in onder if len(c["component_ids"]) == kleinste]
    if len(smalste) == 1 and kleinste <= KLEINE_CONFIGURATOR:
        return smalste[0]
    return None


# --------------------------------------------------------------------------- #
# Normaliseren
# --------------------------------------------------------------------------- #
_GEWICHT = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kilo|kg|gram|gr|g)\b", re.I)


def gewicht_gram(titel):
    """Gewicht uit de titel, of "" als het er niet ondubbelzinnig in staat."""
    m = _GEWICHT.search(titel)
    if not m:
        return ""
    getal = float(m.group(1).replace(",", "."))
    eenheid = m.group(2).lower()
    gram = getal * 1000 if eenheid in ("kilo", "kg") else getal
    return str(int(round(gram)))


def bepaal_prijs(product):
    """Prijs in euro volgens het ingestelde beleid. Nooit geraden."""
    p = product["prices"]
    centen = p["regular_price"] if PRIJS_BASIS == "advies" else p["price"]
    return round(int(centen) / 100 * PRIJS_FACTOR, 2)


def heeft_eigen_pagina(product):
    """Producten zonder categorie staan onder /geen-categorie/ en die URL stuurt
    door naar /winkel/. Alleen de rest heeft een eigen pagina met uitklappers."""
    return "/geen-categorie/" not in product.get("permalink", "")


def fetch_eigen_secties(producten):
    """{product_id: secties} voor de producten met een eigen publieke pagina."""
    uit = {}
    doelen = [p for p in producten if heeft_eigen_pagina(p)]
    print(f"   {len(doelen)} producten hebben een eigen pagina met productinfo")
    for i, p in enumerate(doelen, 1):
        try:
            _, secties = parse_configurator(_get(p["permalink"]).text)
        except Exception as e:
            print(f"    !  Eigen pagina faalt bij {p['slug']}: {e}")
            continue
        if secties:
            uit[p["id"]] = secties
        print(f"  [{i}/{len(doelen)}] {p['name'][:42]:<42} - {len(secties)} secties")
        time.sleep(REQUEST_DELAY)
    return uit


def bouw_beschrijving(product, ouder, eigen_secties=None):
    """Eigen pagina gaat voor, daarna de configurator van de ouder.

    Er wordt niets bijgeschreven of samengevat: elk stuk tekst staat letterlijk
    zo op personalprotein.nl.
    """
    delen = []
    for veld in ("short_description", "description"):
        if product.get(veld):
            delen.append(unescape(product[veld]))

    secties = eigen_secties or (ouder["secties"] if ouder else [])
    if ouder and not eigen_secties and ouder["short"] \
            and not product.get("short_description"):
        delen.append(unescape(ouder["short"]))
    for kop, inhoud in secties:
        delen.append(f"<p><strong>{kop}</strong></p>\n{unescape(inhoud)}")
    return "\n".join(delen)


def kies_producttype(eigen_categorieen, ouder):
    """De eerste echte categorie; anders die van de configurator.

    Producten staan vaak in "Bestseller" of "Summer Sale" voordat ze in
    "Eiwitshakes" staan - en dan zou het producttype in Shopify "Bestseller"
    worden. Ook "Extra's" telt niet mee: dat is de restbak van Personal Protein,
    daar staan vitaminen en pre-workout naast elkaar in.
    """
    for c in eigen_categorieen + (ouder["categorieen"] if ouder else []):
        if c.lower() not in GEEN_PRODUCTTYPE:
            return c
    return ""


def normaliseer(product, ouder, eigen_secties=None):
    eigen_cats = [c["name"] for c in product.get("categories", [])]
    eigen_tags = [t["name"] for t in product.get("tags", [])]
    images = [img["src"] for img in product.get("images", []) if img.get("src")]
    if not images and ouder:
        images = ouder["images"]
    return {
        "id": product["id"],
        "handle": product["slug"],
        "sku": product["sku"],
        "barcode": "",                       # Personal Protein voert geen EAN
        "title": product["name"],
        "vendor": BRAND,
        "brand": BRAND,
        "product_type": kies_producttype(eigen_cats, ouder),
        "tags": ", ".join(dict.fromkeys(eigen_tags + (ouder["tags"] if ouder else []))),
        "description": bouw_beschrijving(product, ouder, eigen_secties),
        "images": images,
        "price": bepaal_prijs(product),
        "prijs_regulier": round(int(product["prices"]["regular_price"]) / 100, 2),
        "prijs_actie": round(int(product["prices"]["price"]) / 100, 2),
        "available": bool(product["is_in_stock"]),
        "weight": gewicht_gram(product["name"]),
        "tekstbron": ("eigen pagina" if eigen_secties
                      else (ouder["naam"] if ouder else "")),
        "ouder": ouder["naam"] if ouder else "",
        "url": product["permalink"],
    }


# --------------------------------------------------------------------------- #
# Zeef — wat wegvalt, valt zichtbaar weg
# --------------------------------------------------------------------------- #
def _reden_overslaan(p):
    if p["type"] != "simple":
        return f"configurator/bundel ({p['type']}) - geen eigen prijs of SKU"
    if not p.get("sku"):
        return "geen SKU"
    if int(p["prices"]["regular_price"]) == 0:
        return "prijs is 0"
    cats = {c["name"].lower() for c in p.get("categories", [])}
    merch = cats & MERCH_CATEGORIEEN
    if merch and not MERCH_MEE:
        return f"merch/accessoire ({', '.join(sorted(merch))})"
    return None


def schrijf_overgeslagen(rijen, pad=OVERGESLAGEN_FILE):
    with open(pad, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku", "naam", "type", "reden"])
        w.writerows(rijen)
    print(f"   Overgeslagen vastgelegd in {pad} ({len(rijen)} regels)")


# --------------------------------------------------------------------------- #
# De hoofdroute
# --------------------------------------------------------------------------- #
def fetch_products(met_teksten=True):
    """De verkoopbare producten, genormaliseerd. De telling sluit altijd.

    met_teksten=False slaat de configurator-pagina's over (de update-feed heeft
    alleen prijs + voorraad nodig).
    """
    ruw = fetch_catalogus()
    print(f"   {len(ruw)} producten uit de Store API")

    overgeslagen, houden = [], []
    for p in ruw:
        reden = _reden_overslaan(p)
        if reden:
            overgeslagen.append([p.get("sku", ""), p["name"], p["type"], reden])
        else:
            houden.append(p)

    test_sku = os.environ.get("TEST_SKU")
    if test_sku:
        houden = [p for p in houden if p["sku"] == test_sku]

    configs, eigen = {}, {}
    if met_teksten:
        eigen = fetch_eigen_secties(houden)
        configurators = [p for p in ruw if p["type"] in ("composite", "bundle")]
        print(f"   {len(configurators)} configurator-pagina's ophalen voor de rest")
        configs = fetch_configurators(configurators)

    uit = [normaliseer(p, kies_ouder(p, configs), eigen.get(p["id"]))
           for p in houden]

    # Telling: elk product uit de bron is of in de feed, of met reden overgeslagen.
    if not test_sku:
        assert len(uit) + len(overgeslagen) == len(ruw), (
            f"Telling klopt niet: {len(uit)} + {len(overgeslagen)} != {len(ruw)}")
        skus = [p["sku"] for p in uit]
        assert len(skus) == len(set(skus)), (
            f"Dubbele SKU in de feed: "
            f"{[s for s in set(skus) if skus.count(s) > 1]}")
        assert all(p["price"] > 0 for p in uit), "Product met prijs 0 in de feed"
        schrijf_overgeslagen(overgeslagen)

    redenen = {}
    for r in overgeslagen:
        kop = r[3].split(" (")[0].split(" -")[0]
        redenen[kop] = redenen.get(kop, 0) + 1
    print(f"\n   TELLING  {len(ruw)} in de bron "
          f"= {len(uit) if not test_sku else '?'} in de feed "
          f"+ {len(overgeslagen)} overgeslagen")
    for kop, n in sorted(redenen.items(), key=lambda x: -x[1]):
        print(f"            - {n:>3}x {kop}")
    if met_teksten and uit:
        met = sum(1 for p in uit if p["description"])
        print(f"   TEKST    {met} van {len(uit)} producten hebben een beschrijving "
              f"({len(uit) - met} zonder)")
    in_voorraad = sum(1 for p in uit if p["available"])
    print(f"   VOORRAAD {in_voorraad} van {len(uit)} op voorraad bij Personal Protein")
    print(f"   PRIJS    basis '{PRIJS_BASIS}'"
          + (f", factor {PRIJS_FACTOR}" if PRIJS_FACTOR != 1.0 else "")
          + "  (advies = reguliere prijs, actueel = met lopende actie)\n")
    return uit


# --------------------------------------------------------------------------- #
# De rem: nooit een halve feed wegschrijven
# --------------------------------------------------------------------------- #
def controleer_omvang(aantal, filepath, tag="<product>"):
    """Stop de run bij een lege of gehalveerde feed.

    Stock Sync zet producten die niet in de feed staan op *gearchiveerd*, stil en
    zonder melding. Op 17-07-2026 om 19:47 schreef de Energetica-scraper 40 van
    de 183 producten weg; de Stock Sync-run van 18-07 om 03:07 archiveerde er 137,
    en die stonden 44 dagen uit Google. Geen enkele feed had toen een ondergrens.

    Een halve uitkomst mag daarom niet worden weggeschreven: dan blijft de vorige
    (goede) feed staan en wordt de GitHub Action rood. Krimpt de leverancier écht,
    dan overrulet FORCE_FEED=1 dit bewust.

    Tel op `<product>`, niet op `<sku>`: een leeg SKU-veld wordt `<sku/>` en telt
    dan niet mee (Goldea telt 44 feed-regels maar 41 `<sku>`).
    """
    vorig = 0
    if os.path.exists(filepath):
        with open(filepath, encoding="utf-8") as f:
            vorig = f.read().count(tag)
    print(f"🧮 {aantal} feed-regels nu, {vorig} in de vorige feed")

    if os.environ.get("FORCE_FEED") == "1":
        print("⚠️  FORCE_FEED=1 — controle overgeslagen.")
        return
    if aantal == 0:
        raise SystemExit(
            "❌ 0 feed-regels gevonden — feed NIET overschreven. Meestal een "
            "gewijzigde bron-URL of een leverancier die plat ligt."
        )
    if vorig and aantal < vorig * 0.5:
        raise SystemExit(
            f"❌ Slechts {aantal} van de {vorig} feed-regels gevonden (<50%) — feed "
            "NIET overschreven. Controleer de bron; forceren kan met FORCE_FEED=1."
        )
    if vorig and aantal < vorig * 0.9:
        print(f"⚠️  {aantal} van {vorig} feed-regels ({aantal / vorig:.0%}) — flinke "
              "daling, feed wél geschreven. Controleer of dat klopt.")
