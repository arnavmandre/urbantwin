-- Argus run history for Grafana. Runs once, on the first start of an empty
-- volume. To apply changes: docker compose -f analytics/docker-compose.yml down -v
--
-- Everything here is copied from simulator output (data/runs/<id>/) or from
-- the API's terminal-status log (data/run_events.jsonl). Nothing is observed
-- weather and nothing is validated against real outcomes.

CREATE SCHEMA analytics;

CREATE TABLE analytics.simulation_runs (
    run_id            text PRIMARY KEY,
    status            text NOT NULL CHECK (status IN ('complete', 'failed', 'cancelled')),
    created_at        timestamptz NOT NULL,
    -- From the API event log only; NULL for runs it did not see (CLI runs,
    -- runs before the log existed).
    finished_at       timestamptz,
    -- Sum of the pipeline's recorded stage times. Complete runs only.
    pipeline_seconds  double precision,
    -- The --city argument the simulation stage ran with, e.g. city_osm.json.
    city_id           text,
    -- Preset whose four inputs match exactly; NULL means custom inputs.
    scenario_preset   text,
    intervention      text,
    error_code        text,
    -- 'run_manifest' (data/runs/<id>/) or 'api_event' (failed/cancelled only).
    record_source     text NOT NULL,
    source_path       text,
    imported_at       timestamptz NOT NULL DEFAULT now()
);

-- Inputs typed into the scenario, never measurements.
CREATE TABLE analytics.scenario_inputs (
    run_id                text PRIMARY KEY REFERENCES analytics.simulation_runs ON DELETE CASCADE,
    temperature_c         double precision,
    humidity_pct          double precision,
    rainfall_prototype    double precision,
    population_equivalent integer,
    value_kind            text NOT NULL DEFAULT 'scenario_input'
);

-- One row per run, arm and metric. 'baseline' is the report's before arm and
-- 'intervention' its after arm: same run, same scenario, same definitions.
-- Metrics missing from a report are absent here, never stored as zero.
CREATE TABLE analytics.simulation_metrics (
    run_id            text NOT NULL REFERENCES analytics.simulation_runs ON DELETE CASCADE,
    arm               text NOT NULL CHECK (arm IN ('baseline', 'intervention')),
    metric_name       text NOT NULL,
    metric_label      text NOT NULL,
    metric_value      double precision NOT NULL,
    unit              text NOT NULL,
    higher_is_better  boolean NOT NULL,
    PRIMARY KEY (run_id, arm, metric_name)
);

-- Simulator parameters the intervention arm applied, e.g. drainage_boost 0.35.
CREATE TABLE analytics.interventions (
    run_id     text NOT NULL REFERENCES analytics.simulation_runs ON DELETE CASCADE,
    parameter  text NOT NULL,
    value      double precision NOT NULL,
    PRIMARY KEY (run_id, parameter)
);

CREATE INDEX ON analytics.simulation_runs (created_at);

-- Baseline vs intervention per run and metric. Relative change is NULL when
-- the baseline is zero, where a percentage would be meaningless.
CREATE VIEW analytics.metric_comparison AS
SELECT
    b.run_id,
    b.metric_name,
    b.metric_label,
    b.unit,
    b.higher_is_better,
    b.metric_value                       AS baseline,
    i.metric_value                       AS intervention,
    i.metric_value - b.metric_value      AS abs_change,
    CASE WHEN b.metric_value = 0 THEN NULL
         ELSE 100.0 * (i.metric_value - b.metric_value) / abs(b.metric_value)
    END                                  AS rel_change_pct,
    CASE WHEN abs(i.metric_value - b.metric_value) < 0.005 THEN 'unchanged'
         WHEN (i.metric_value > b.metric_value) = b.higher_is_better THEN 'better'
         ELSE 'worse'
    END                                  AS outcome
FROM analytics.simulation_metrics b
JOIN analytics.simulation_metrics i
  ON i.run_id = b.run_id AND i.metric_name = b.metric_name AND i.arm = 'intervention'
WHERE b.arm = 'baseline';

-- Grafana's read-only role is created in 02_grafana_reader.sh, which can read
-- the password from the container environment.
