# Data ingestion

## Step 1 — pull a candidate region's HAPI export (no account needed)

```
pip install -r requirements.txt
python fetch_hdx_dataset.py hdx-hapi-syr
python fetch_hdx_dataset.py hdx-hapi-irq
python fetch_hdx_dataset.py hdx-hapi-hti
python fetch_hdx_dataset.py hdx-hapi-eth
python fetch_hdx_dataset.py hdx-hapi-som
```

Each run drops the dataset's resource files into `raw/<dataset_id>/`. Open a couple of these and pick the region whose location data goes down to admin1/admin2 level with recent food security + displacement figures — that's what makes "allocate across locations" a real model instead of one national number.

The script hits HDX's standard CKAN API (`https://data.humdata.org/api/3/action/package_show`), which needs no authentication for reads — confirmed directly from HDX's own API docs, not assumed.

## Step 2 — (optional, later) live HAPI API for fresher data

Once a region is picked and the core build works, `https://hapi.humdata.org` has a live query API for the same indicators, filterable by `location_code`. It needs a free `app_identifier` — generate one with:

```
curl "https://hapi.humdata.org/api/v1/encode_app_identifier?application=ctrl-alt-conquer&email=chvms7712@gmail.com"
```

Only the general URL shape and the food-security endpoint path (`food-security-nutrition-poverty/food-security`) were directly confirmed this session — the exact slugs for the displacement and funding endpoints weren't, so check `https://hapi.humdata.org/docs` before wiring those up. This is a "go big" upgrade, not something the core build depends on.

## Step 3 — supplementary market-level food prices (optional)

WFP's Global Food Prices dataset on HDX (`wfp-food-prices` / `global-wfp-food-prices`) covers ~98 countries and ~3,000 markets with HXL-tagged CSVs, if the chosen region needs more granular market-level food pricing than HAPI's food-security indicator alone provides.
