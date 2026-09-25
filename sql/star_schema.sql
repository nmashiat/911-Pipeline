-- Star schema for SF Fire/EMS calls.
-- Grain: fact_unit_response = one unit's response to one call (matches source).
--        fact_call          = one call, rolled up from its units.
-- Dimensions are small lookup tables keyed by a surrogate integer id.

CREATE TABLE IF NOT EXISTS dim_date (
    date_key      INTEGER PRIMARY KEY,   -- yyyymmdd
    full_date     TEXT NOT NULL UNIQUE,
    year          INTEGER, month INTEGER, day INTEGER,
    day_of_week   INTEGER,               -- 0=Sunday ... 6=Saturday
    is_weekend    INTEGER
);

CREATE TABLE IF NOT EXISTS dim_call_type (
    call_type_key   INTEGER PRIMARY KEY AUTOINCREMENT,
    call_type       TEXT NOT NULL,
    call_type_group TEXT,
    UNIQUE (call_type, call_type_group)
);

CREATE TABLE IF NOT EXISTS dim_unit (
    unit_key   INTEGER PRIMARY KEY AUTOINCREMENT,
    unit_id    TEXT NOT NULL,
    unit_type  TEXT,
    UNIQUE (unit_id, unit_type)
);

CREATE TABLE IF NOT EXISTS dim_neighborhood (
    neighborhood_key    INTEGER PRIMARY KEY AUTOINCREMENT,
    neighborhood        TEXT NOT NULL UNIQUE,
    supervisor_district TEXT,
    battalion           TEXT
);

CREATE TABLE IF NOT EXISTS fact_unit_response (
    rowid_src            TEXT PRIMARY KEY,   -- source rowid, natural key
    call_number          TEXT NOT NULL,
    date_key             INTEGER REFERENCES dim_date(date_key),
    call_type_key        INTEGER REFERENCES dim_call_type(call_type_key),
    unit_key             INTEGER REFERENCES dim_unit(unit_key),
    neighborhood_key     INTEGER REFERENCES dim_neighborhood(neighborhood_key),
    received_dttm        TEXT NOT NULL,
    dispatch_dttm        TEXT,
    on_scene_dttm        TEXT,
    available_dttm       TEXT,
    priority             TEXT,
    als_unit             INTEGER,
    unit_sequence        INTEGER,
    -- derived intervals, seconds. NULL when either timestamp missing or order is invalid.
    secs_to_dispatch     INTEGER,
    secs_dispatch_to_scene INTEGER,
    secs_to_scene        INTEGER,
    load_date            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fur_load_date ON fact_unit_response(load_date);
CREATE INDEX IF NOT EXISTS ix_fur_call ON fact_unit_response(call_number);

CREATE TABLE IF NOT EXISTS fact_call (
    call_number          TEXT PRIMARY KEY,
    date_key             INTEGER REFERENCES dim_date(date_key),
    call_type_key        INTEGER REFERENCES dim_call_type(call_type_key),
    neighborhood_key     INTEGER REFERENCES dim_neighborhood(neighborhood_key),
    received_dttm        TEXT NOT NULL,
    first_dispatch_dttm  TEXT,
    first_on_scene_dttm  TEXT,
    units_dispatched     INTEGER,
    units_on_scene       INTEGER,
    final_priority       TEXT,
    -- response time = received -> first unit on scene. The metric people mean by "response time".
    response_secs        INTEGER,
    load_date            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fc_load_date ON fact_call(load_date);
