-- Myanmar need-score model -- deliberately NOT a copy of Syria's.
-- Syria has no sector-specific need data, so need_score is the same
-- regardless of resource_type. Myanmar's real humanitarian_needs data
-- IS broken down by sector (SHL/FSC/HEA all confirmed present, same
-- latest period, checked before writing this), so its need_score
-- genuinely varies by resource_type -- a real capability the
-- architecture uses when the underlying data supports it, not a
-- uniform template stamped onto every crisis.
--
-- admin_level = 1 confirmed INTEGER via `bq show` before writing this
-- (same INTEGER-not-STRING gotcha hit with Syria's admin_level).

CREATE OR REPLACE VIEW crisis_allocator.mmr_state_centroid AS
SELECT
  admin1_name,
  AVG(lat) AS lat,
  AVG(lon) AS lon
FROM crisis_allocator.raw_food_price_mmr
WHERE lat IS NOT NULL AND lon IS NOT NULL AND admin1_name IS NOT NULL
GROUP BY admin1_name;

-- One row per (state, sector) at the latest real reporting period
-- (2025-12-08 as of this session -- the 2026 HNRP's underlying needs
-- assessment, not stale data; confirmed by checking actual periods
-- present, not assumed). category = 'total' specifically excludes the
-- demographic breakdown rows (Adult/Children/Female/etc.) that sit
-- alongside it in the same file -- summing those in by accident would
-- have multi-counted every person.
CREATE OR REPLACE VIEW crisis_allocator.mmr_need_score AS
SELECT
  n.admin1_name AS district_name,
  n.admin1_code AS district_code,
  n.sector_code,
  n.population AS need_score,
  c.lat,
  c.lon
FROM (
  SELECT admin1_name, admin1_code, sector_code, population, reference_period_end
  FROM crisis_allocator.raw_humanitarian_needs_mmr
  WHERE admin_level = 1
    AND population_status = 'INN'
    AND category = 'total'
    AND sector_code IN ('SHL', 'FSC', 'HEA')
) n
LEFT JOIN crisis_allocator.mmr_state_centroid c
  ON n.admin1_name = c.admin1_name
WHERE n.reference_period_end = (
  SELECT MAX(reference_period_end)
  FROM crisis_allocator.raw_humanitarian_needs_mmr
  WHERE admin_level = 1 AND population_status = 'INN' AND category = 'total'
);
