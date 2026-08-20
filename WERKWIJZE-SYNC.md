# Personal Protein — sync-werkwijze

Runbook om Personal Protein in Shopify te krijgen. **Volg de volgorde.** Stap 0
moet echt eerst, anders staat er straks iets in de winkel dat de NVWA niet mag
zien.

Feeds (GitHub → Actions → Run workflow):

```
UPDATE: https://raw.githubusercontent.com/Maximillian-creator/personalprotein-feed/main/personalprotein_feed.xml
ADD:    https://raw.githubusercontent.com/Maximillian-creator/personalprotein-feed/main/personalprotein_add_feed.xml
```

---

## Stap 0 — Repo op publiek zetten ⟵ EERST, anders werkt de rest niet

Stock Sync haalt de feed op via `raw.githubusercontent.com` en heeft daar geen
inloggegevens voor. Bij een privérepo krijgt hij **404** en denkt hij dat de feed
leeg is. Alle andere leveranciersfeeds (Goldea, Vitakruid, Deltastar…) staan om
diezelfde reden publiek.

> GitHub → repo `personalprotein-feed` → **Settings** → onderaan **Danger Zone**
> → *Change repository visibility* → **Public**.

Wat er dan openbaar staat: de scripts en de twee XML's met productinfo die al
openbaar op personalprotein.nl staat. Geen sleutels, geen inkoopprijzen — die
zitten hier ook niet in, want de feed gebruikt de publieke consumentenprijs.

## Stap 1 — Feeds één keer handmatig draaien

GitHub → **Actions** → *Personal Protein Feed Updater* → **Run workflow**, en
daarna *Personal Protein ADD-feed Updater*. De update-feed is in seconden klaar,
de add-feed doet er een paar minuten over (die haalt ~70 pagina's op).

Daarna draaien ze vanzelf: update 2× per dag (06:00 + 18:00 UTC), add elke
maandag 04:00 UTC.

## Stap 2 — Add-feed → Stock Sync "Add Products"

1. Nieuwe connectie, bron **XML via URL**, de ADD-URL hierboven.
2. Record-pad `/products/product`, groeperen op **Handle**.
3. Mapping:

| Stock Sync veld | XPath |
|---|---|
| Handle | `handle` |
| Title | `title` |
| Body HTML / Description | `description` |
| Vendor | `vendor` (= Personal Protein) |
| Type | `product_type` |
| Tags | `tags` |
| Image Src *(meerdere)* | `images/image/src` |
| Variant SKU | `variants/variant/sku` |
| Variant Price | `variants/variant/price` |
| Variant Weight | `variants/variant/weight` (gram) |

4. Zet de koppeling op **alleen nieuwe producten aanmaken** en laat producten op
   **Draft** binnenkomen. De feed zet `published` zelf al op `false`.
5. **Barcode niet mappen** — Personal Protein voert geen EAN. Het veld staat leeg
   in de feed en een leeg barcodeveld kan bestaande barcodes overschrijven.

Verwacht resultaat: **76 producten**, allemaal op concept.

## Stap 3 — Themis vóór je iets op Active zet

```bash
python themis_check.py
```

Dat leest de add-feed en schrijft `personalprotein_themis.md`. Stand bij
oplevering: **56 ok · 8 let op · 10 afkeuren**. De teksten zijn letterlijk die
van Personal Protein, en die claimen dingen die wij niet mogen claimen —
collageen is het scherpst (NVWA-actie augustus 2025), daarna magnesium,
vitamine D3 en omega-3.

Publiceer geen product waarvan de tekst op *afkeuren* staat voordat die tekst is
herschreven. Dit is precies het werk waar Nova voor is.

## Stap 4 — Update-feed → Stock Sync "Update"

Nieuwe connectie met de UPDATE-URL, modus **Update**, match op **SKU**.
Map alleen `price` en `available`. Meer niet — deze feed is bewust mager, zodat
hij nooit per ongeluk een beschrijving of afbeelding overschrijft.

## Stap 5 — Wat je NIET moet aanzetten

- **Geen automatische verwijderregel.** Als je er later toch een wilt: actie =
  *Draft/archiveren*, nooit hard verwijderen, en keihard filteren op
  `vendor = Personal Protein` — anders raakt de regel ook Deltastar, Vitalized,
  Energetica, Goldea en Supplement Hub.
- **Geen compare-at-prijs.** De feed levert er geen, en verzint er geen.

---

## Wat er bewust buiten de feed blijft

`personalprotein_overgeslagen.csv` in de repo noemt ze allemaal met reden. Kort:

| aantal | wat | waarom |
|---|---|---|
| 31 | configurators ("kies je maat + 2 gratis shots") | die geven prijs €0,00 terug in de API |
| 5 | shaker, handdoek, tote bag, refill jar | merch, geen supplement — aanzetten met `PP_MERCH=1` |
| 1 | "Pack" | prijs 0 |

## Prijs

`price` = de **reguliere** consumentenprijs incl. BTW, dus zonder de lopende
Summer Sale (57 van de 76 staan in de aanbieding). Afgesproken 20-08-2026.
Wil je het anders: `PP_PRIJS_BASIS=actueel` of `PP_PRIJS_FACTOR=1.05` als env in
de workflow.

## Rollback

- Producten komen op **Draft** binnen — niets is zichtbaar tot jij het op Active
  zet.
- Gaat de add-feed mis: de aangemaakte producten hebben allemaal
  `vendor = Personal Protein`, dus in Shopify in één filter terug te vinden.
- `python test_feed.py` controleert vóór elke commit dat de telling sluit, dat er
  geen dubbele SKU's zijn en dat geen enkel product een prijs van 0 heeft.
