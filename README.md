# Personal Protein feeds → Stock Sync

Scrapt de publieke **WooCommerce**-winkel van Personal Protein
(`personalprotein.nl`) en maakt twee XML-feeds voor
[Stock Sync](https://stock-sync.com). Beide draaien via GitHub Actions.

| Feed | Script | Output | Doel | Schema |
|---|---|---|---|---|
| **Update-feed** | `scraper.py` | `personalprotein_feed.xml` | Prijs + beschikbaarheid van **bestaande** producten | 2× per dag (06:00 + 18:00 UTC) |
| **Add-feed** | `add_scraper.py` | `personalprotein_add_feed.xml` | **Nieuwe** producten aanmaken met álle info | 1× per week (ma 04:00 UTC) |

## Feed-URL's (Stock Sync)

```
Update:  https://raw.githubusercontent.com/Maximillian-creator/personalprotein-feed/main/personalprotein_feed.xml
Add:     https://raw.githubusercontent.com/Maximillian-creator/personalprotein-feed/main/personalprotein_add_feed.xml
```

## Wat er in de feed zit — en wat niet

De catalogus heeft **113 producten**, maar dat zijn niet 113 dingen die je kunt
kopen:

| | aantal | |
|---|---|---|
| `simple` | 82 | de échte SKU's met prijs en voorraad |
| `composite` | 30 | configurators: "kies je maat + 2 gratis flavour shots" |
| `bundle` | 1 | idem |

De configurators geven in de API **prijs `"0"`** terug — hun prijs hangt af van
wat je kiest. Wie die klakkeloos overneemt, zet 31 producten van €0,00 in de
winkel. Ze gaan daarom **niet** de feed in; ze dienen alleen als tekstbron.

Wat er per run overblijft (stand 20-08-2026):

```
113 in de bron = 76 in de feed + 37 overgeslagen
                                  31x configurator/bundel
                                   5x merch/accessoire (shaker, handdoek, tote bag, refill jar)
                                   1x prijs is 0 ("Pack")
```

Elk overgeslagen product staat mét reden in **`personalprotein_overgeslagen.csv`**
— er verdwijnt niets stilletjes. Merch mee laten doen? `PP_MERCH=1`.

## Bronnen & bijzonderheden

- **WooCommerce Store API** (`/wp-json/wc/store/v1/products`) → sku, reguliere
  prijs én actieprijs, voorraad, afbeeldingen, categorieën, tags, korte
  beschrijving. Publiek, geen login, geen sleutel.
- **De configurator-pagina's** → de uitklapsecties *Beschrijving*,
  *Ingrediënten*, *Voedingswaarden* (de hele tabel, inclusief aminozuren) en
  *Gebruik*. De sectie *Support* wordt overgeslagen: daar staat het
  telefoonnummer van Personal Protein in.
- **Losse SKU-pagina's bestaan niet.** Producten zonder categorie staan onder
  `/producten/geen-categorie/…` en die URL stuurt door naar `/winkel/`. Hun
  tekst komt dus van de configurator waar ze onder hangen.
- **Geen EAN/GTIN.** Nergens: niet in de API, niet in schema.org, niet in de
  HTML. `barcode` blijft leeg en Stock Sync matcht op **SKU**. Voor Google
  Merchant Center betekent dat: geen GTIN, dus `identifier_exists: no` of de
  EAN's later zelf aanvullen.
- **Voorraad is in/uit**, geen aantal. Map `available` op beschikbaarheid.

### Waar de tekst per product vandaan komt

`personalprotein_tekstbron.csv` legt dat per SKU vast, zodat "74 van de 76
hebben een beschrijving" een controleerbare regel is en geen belofte:

| tekstbron | aantal |
|---|---|
| eigen pagina | 20 |
| via de configurator van de ouder | 40 |
| alleen de korte omschrijving (±22 woorden) | 14 |
| geen tekst | 2 |

De 14 magere gevallen zijn bijna allemaal **uitverkochte flavour shots**: hun
pagina rendert dan zonder uitklappers. Komen ze terug op voorraad, dan pikt de
volgende wekelijkse run de tekst alsnog op. De 2 zonder tekst zijn
`lmps1kg` (Les Mills) en `wpi2kg` (een oude 2KG-SKU die op de winkel niet meer
te vinden is — mogelijk gewoon vervallen).

## Prijs & voorraad

`price` = de **reguliere consumentenprijs incl. BTW**, dus zónder de lopende
Summer Sale. Dat is bewust: 57 van de 76 producten staan nú in de aanbieding, en
je wilt niet dat de winkelprijs van Good For You meebeweegt met de actie van een
ander.

| env | betekenis |
|---|---|
| `PP_PRIJS_BASIS=advies` | reguliere prijs (**standaard**) |
| `PP_PRIJS_BASIS=actueel` | de prijs van vandaag, inclusief actie |
| `PP_PRIJS_FACTOR=1.05` | alle prijzen × 1,05 |

`compare_at_price` blijft altijd leeg — er wordt geen doorgestreepte prijs
verzonnen.

## Compliance — lees dit vóór je publiceert

De beschrijvingen zijn **letterlijk die van Personal Protein**. Wat daar staat
mag bij ons niet automatisch ook staan; wij zijn zelf aansprakelijk voor elke
claim. Daarom:

- `published` staat in de add-feed hard op **`false`**. Zet de Stock
  Sync-koppeling op *alleen nieuwe producten aanmaken* en laat ze op concept.
- `python themis_check.py` haalt elke beschrijving door `gfy-themis` en schrijft
  **`personalprotein_themis.md`**. Stand 20-08-2026: **56 ok · 8 let op ·
  10 afkeuren**. De afkeuringen zitten vooral bij collageen (NVWA handhaaft daar
  actief op), magnesium, vitamine D3 en omega-3.
- Themis draait alleen lokaal, in de map `Claude Code Projecten` waar
  `gfy-themis` naast deze repo staat. In Actions slaat het script zichzelf over.

## Stock Sync mapping (Add products)

Type **"Add Products"**, bronformaat XML, record-pad `/products/product`,
groepeer op **Handle**.

| Stock Sync veld | XPath |
|---|---|
| Handle | `handle` |
| Title | `title` |
| Body HTML / Description | `description` |
| Vendor | `vendor` (= Personal Protein) |
| Type | `product_type` |
| Tags | `tags` |
| Image Src *(meerdere)* | `images/image/src` *(of `image_links`)* |
| Variant SKU | `variants/variant/sku` |
| Variant Price | `variants/variant/price` *(incl. BTW)* |
| Variant Weight | `variants/variant/weight` *(gram; leeg als het niet in de titel stond)* |

Voor de **Update**-koppeling: match op `sku`, en map `price` en `available`.

## Lokaal draaien / testen

```bash
pip install -r requirements.txt
python scraper.py                    # update-feed (~3 s)
python add_scraper.py                # add-feed (~70 pagina's, een paar minuten)
python test_feed.py                  # invarianten: telling, dubbelen, prijs > 0
python themis_check.py               # claimcontrole → personalprotein_themis.md
```

| env | waarvoor |
|---|---|
| `INSECURE_SSL=1` | achter een SSL-onderscheppende proxy (thuis nodig) |
| `TEST_SKU=wpi1kg` | één product |
| `PP_CACHE_DIR=…` | pagina's op schijf bewaren tijdens ontwikkelen |
| `PYTHONIOENCODING=utf-8` | Windows-console |
