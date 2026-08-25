# Chaska real catalog source manifest

This directory contains a research manifest for 30 currently listed restaurant
branches and 90 published menu items (three per restaurant). It is not a seed and
does not perform any database operation.

## Files

- `restaurants.json` contains records shaped to the v1 restaurant contract.
- `dishes.json` contains records shaped to the v1 dish contract.
- `sources.json` keeps branch/address/menu evidence separately from public records.
- `build_manifest.py` deterministically rebuilds and validates the three JSON files.

There are deliberately zero deal records. Platform promotions were not converted
to Chaska deals.

## Evidence policy

Restaurant names, branches, addresses or verified localities, menu item names,
regular prices, and any included descriptions come from the URLs in
`sources.json`. `address_verification_status=exact` means the listing exposed a
street-level or venue-level address. `area_verified` means only the named branch
and locality were retained. Coordinates are null because no branch-specific
coordinate pair was confidently verified. Halal status is `unknown` throughout;
no claim is inferred from cuisine, geography, or brand reputation.

Where a listing displayed a temporary platform discount alongside an original
price, the manifest stores the original regular price. Items with only an
ambiguous `from` price were avoided. A few menu entries that appeared as a
single-priced popular item were accepted even if another menu section offered
configurable variants.

Ingredients remain empty unless a source published a sufficiently clear list.
Descriptions are included only when supported by the menu listing. Empty
allergen and dietary arrays mean “not catalogued,” not allergen-free or suitable
for a particular diet.

## Editorial taste values

The required 0–5 taste-profile numbers and texture tags are conservative editorial
estimates for cold-start recommendation bootstrapping. They are derived from the
sourced dish name, cuisine and published preparation/description, but are not
restaurant-published facts. Applications must not display them as claims made by
the restaurant.

## Validation

Run locally without application imports or network/database access:

```powershell
python data/real_catalog/build_manifest.py
```

The validator checks counts, city split, three dishes per restaurant, unique
normalized brands, references, positive numeric prices, coordinate pairing,
unsupported halal claims, forbidden regional cuisine labels, source URLs, and
sample-data markers. It also parses every emitted JSON file.

Failed/replaced candidates are documented under `failed_candidates` in
`sources.json`.
