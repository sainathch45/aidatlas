-- Crisis Resource Allocator — BigQuery, Sandbox mode (no billing account
-- needed; 1 TiB queries/month, 10 GiB storage, tables auto-expire after
-- 60 days, which is irrelevant for a 9-day build).
--
-- Rewritten 2026-10-09 against the REAL columns of the Syria HAPI export
-- (data/raw/hdx-hapi-syr/*.csv), confirmed by actually downloading and
-- inspecting it this session -- not guessed.

CREATE SCHEMA IF NOT EXISTS crisis_allocator;

-- Raw tables are loaded by bigquery/load_syria_data.sh (bq load
-- --autodetect against the real downloaded CSVs) -- run that first.
-- Column reference, confirmed from the real files, not guessed:
--
-- (raw_idps columns: location_code, has_hrp, in_gho, provider_admin1_name,
--  provider_admin2_name, admin1_code, admin1_name, admin2_code,
--  admin2_name, admin_level, operation, assessment_type, population,
--  reporting_round, reference_period_start, reference_period_end)
--
-- (raw_operational_presence adds: org_acronym, org_name,
--  org_type_description, sector_code, sector_name)
--
-- (raw_funding: location_code, appeal_code, appeal_name, appeal_type,
--  requirements_usd, funding_usd, funding_pct, reference_period_start,
--  reference_period_end -- confirmed real row: appeal_code 'HSYR26',
--  requirements_usd 2,922,184,830, funding_usd 935,449,756, funding_pct 32)

-- Real "need" signal: IDP population by admin2 district, most recent
-- reporting round only. admin_level = 2 filters out the national (0) and
-- admin1 (1) rollup rows that sit alongside the district-level ones in
-- the same file.
CREATE OR REPLACE VIEW crisis_allocator.latest_idps_by_district AS
SELECT
  admin1_name,
  admin2_name,
  admin2_code,
  population AS idp_population,
  reference_period_end
FROM crisis_allocator.raw_idps
WHERE admin_level = '2'
  AND reference_period_end = (SELECT MAX(reference_period_end) FROM crisis_allocator.raw_idps WHERE admin_level = '2');

-- Real "existing coverage" signal: how many distinct responding
-- organizations are already active in each district, across all sectors.
-- Used to down-weight need where response capacity already exists,
-- rather than allocating purely by raw population.
CREATE OR REPLACE VIEW crisis_allocator.org_presence_by_district AS
SELECT
  admin2_code,
  COUNT(DISTINCT org_acronym) AS active_org_count
FROM crisis_allocator.raw_operational_presence
GROUP BY admin2_code;

-- The view the allocation model actually reads: need per district,
-- discounted by existing presence. supply_pool_usd is a constant pulled
-- from the real HSYR26 appeal row (funding_usd), not per-district --
-- the model's job is to split that real, currently-32%-funded pool
-- across districts in proportion to this need score.
CREATE OR REPLACE VIEW crisis_allocator.district_need_score AS
SELECT
  d.admin1_name,
  d.admin2_name,
  d.admin2_code,
  d.idp_population,
  COALESCE(p.active_org_count, 0) AS active_org_count,
  d.idp_population / (1 + COALESCE(p.active_org_count, 0)) AS need_score
FROM crisis_allocator.latest_idps_by_district d
LEFT JOIN crisis_allocator.org_presence_by_district p
  USING (admin2_code);

-- Output of the allocation model: one row per decision, meant to be the
-- audit trail that also gets mirrored into Firestore for the live
-- dashboard. This table's shape is unchanged from the first draft.
CREATE TABLE IF NOT EXISTS crisis_allocator.allocations (
  allocation_id   STRING NOT NULL,
  run_timestamp   TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  admin2_code     STRING NOT NULL,
  admin2_name     STRING,
  resource_type   STRING NOT NULL,   -- 'food' | 'medicine' | 'shelter'
  quantity_allocated NUMERIC,
  need_score      NUMERIC,
  supply_available   NUMERIC,
  rationale_text  STRING,            -- Gemini's plain-language explanation for this row
  scenario_label  STRING             -- NULL for the live baseline; set for "what-if" simulation runs
);
