#!/usr/bin/env bash
# Loads the real downloaded Syria HAPI CSVs into BigQuery Sandbox (no
# billing account needed). Run after `gcloud init` has set the active
# project to the one backing this build.
#
#   bash bigquery/load_syria_data.sh

set -euo pipefail
cd "$(dirname "$0")/../data/raw/hdx-hapi-syr"

bq mk --dataset --description "AidAtlas crisis allocator — Syria" crisis_allocator 2>/dev/null || true

bq load --autodetect --source_format=CSV --skip_leading_rows=1 \
  crisis_allocator.raw_idps hdx_hapi_idps_syr.csv

bq load --autodetect --source_format=CSV --skip_leading_rows=1 \
  crisis_allocator.raw_operational_presence hdx_hapi_operational_presence_syr.csv

bq load --autodetect --source_format=CSV --skip_leading_rows=1 \
  crisis_allocator.raw_funding hdx_hapi_funding_syr.csv

bq load --autodetect --source_format=CSV --skip_leading_rows=1 \
  crisis_allocator.raw_food_price hdx_hapi_food_price_syr.csv

echo "Loaded. Now run the view/table definitions:"
echo "  bq query --use_legacy_sql=false < ../../bigquery/schema.sql"
