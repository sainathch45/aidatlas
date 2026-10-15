-- Parali Setu seasonal demand forecast (PRD docs/PARALI_SETU_PRD.md,
-- Section 12). Trained once, offline, during data seeding on the
-- ~104-point-per-series synthetic corpus (seed/forecast_training_corpus.csv)
-- -- not called live during the demo. One time series per company,
-- since each demo company maps 1:1 to a product/region in the seed data.

CREATE OR REPLACE MODEL `parali_setu.demand_forecast_model`
OPTIONS (
  model_type = 'ARIMA_PLUS',
  time_series_timestamp_col = 'week_start',
  time_series_data_col = 'demand_units',
  time_series_id_col = 'company_id',
  auto_arima = TRUE,
  data_frequency = 'WEEKLY'
) AS
SELECT week_start, company_id, demand_units
FROM `parali_setu.demand_history`;

-- 8-week-ahead forecast per company, joined back to product/region so the
-- dashboard doesn't need a second lookup.
CREATE OR REPLACE VIEW `parali_setu.demand_forecast_next_8_weeks` AS
SELECT
  f.company_id,
  ANY_VALUE(h.product) AS product,
  ANY_VALUE(h.region) AS region,
  f.forecast_timestamp AS week_start,
  f.forecast_value AS predicted_demand,
  f.prediction_interval_lower_bound,
  f.prediction_interval_upper_bound
FROM ML.FORECAST(
  MODEL `parali_setu.demand_forecast_model`,
  STRUCT(8 AS horizon, 0.8 AS confidence_level)
) f
JOIN `parali_setu.demand_history` h USING (company_id)
GROUP BY f.company_id, f.forecast_timestamp, f.forecast_value,
         f.prediction_interval_lower_bound, f.prediction_interval_upper_bound
ORDER BY f.company_id, f.forecast_timestamp;
