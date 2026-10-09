#!/usr/bin/env bash
# Loads the real downloaded Myanmar HAPI CSVs into the same BigQuery
# dataset as Syria. Mirrors load_syria_data.sh.
set -euo pipefail
cd "$(dirname "$0")/../data/raw/hdx-hapi-mmr"

bq load --autodetect --source_format=CSV --skip_leading_rows=1 \
  crisis_allocator.raw_humanitarian_needs_mmr hdx_hapi_humanitarian_needs_mmr.csv

bq load --autodetect --source_format=CSV --skip_leading_rows=1 \
  crisis_allocator.raw_funding_mmr hdx_hapi_funding_mmr.csv

bq load --autodetect --source_format=CSV --skip_leading_rows=1 \
  crisis_allocator.raw_food_price_mmr hdx_hapi_food_price_mmr.csv

echo "Loaded. Now run bigquery/schema_myanmar.sql"
