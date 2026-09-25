-- Postgres version of the star schema. Same tables and columns as star_schema.sql;
-- real TIMESTAMP/DATE types, SERIAL keys, and indexes.

CREATE TABLE IF NOT EXISTS dim_date (
    date_key      INTEGER PRIMARY KEY,
    full_date     DATE NOT NULL UNIQUE,
    year          INTEGER, month INTEGER, day INTEGER,
    day_of_week   INTEGER,
    is_weekend    INTEGER
);

CREATE TABLE IF NOT EXISTS dim_call_type (
    call_type_key   SERIAL PRIMARY KEY,
    call_type       TEXT NOT NULL,
    call_type_group TEXT,
    UNIQUE (call_type, call_type_group)
);

CREATE TABLE IF NOT EXISTS dim_unit (
    unit_key   SERIAL PRIMARY KEY,
    unit_id    TEXT NOT NULL,
    unit_type  TEXT,
    UNIQUE (unit_id, unit_type)
);

CREATE TABLE IF NOT EXISTS dim_neighborhood (
    neighborhood_key    SERIAL PRIMARY KEY,
    neighborhood        TEXT NOT NULL UNIQUE,
    supervisor_district TEXT,
    battalion           TEXT
);

CREATE TABLE IF NOT EXISTS fact_unit_response (
    rowid_src            TEXT PRIMARY KEY,
    call_number          TEXT NOT NULL,
    date_key             INTEGER REFERENCES dim_date(date_key),
    call_type_key        INTEGER REFERENCES dim_call_type(call_type_key),
    unit_key             INTEGER REFERENCES dim_unit(unit_key),
    neighborhood_key     INTEGER REFERENCES dim_neighborhood(neighborhood_key),
    received_dttm        TIMESTAMP NOT NULL,
    dispatch_dttm        TIMESTAMP,
    on_scene_dttm        TIMESTAMP,
    available_dttm       TIMESTAMP,
    priority             TEXT,
    als_unit             INTEGER,
    unit_sequence        INTEGER,
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
    received_dttm        TIMESTAMP NOT NULL,
    first_dispatch_dttm  TIMESTAMP,
    first_on_scene_dttm  TIMESTAMP,
    units_dispatched     INTEGER,
    units_on_scene       INTEGER,
    final_priority       TEXT,
    response_secs        INTEGER,
    load_date            TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fc_load_date ON fact_call(load_date);
