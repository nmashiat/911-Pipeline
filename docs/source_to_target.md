# Source → target mapping

| Source field (API) | Staging | Fact / dim | Notes |
|---|---|---|---|
| rowid | rowid | fact_unit_response.rowid_src | natural key, dedupe key |
| call_number | call_number | fact_unit_response, fact_call PK | |
| unit_id, unit_type | same | dim_unit | |
| call_type, call_type_group | same | dim_call_type | |
| neighborhoods_analysis_boundaries | same | dim_neighborhood.neighborhood | |
| received_dttm … available_dttm | same, ISO text | fact_unit_response | parsed with pandas; unparseable → reject |
| case_location (GeoJSON point) | longitude, latitude | — | flattened; missing allowed |
| number_of_alarms, unit_sequence_in_call_dispatch | INTEGER | fact_unit_response.unit_sequence | |
| als_unit | INTEGER 0/1 | fact_unit_response.als_unit | |
| priority fields | TEXT | fact_unit_response.priority, fact_call.final_priority | letters possible |
| data_as_of, data_loaded_at | same | — | used to pick latest on dedupe |
| all others | TEXT | — | kept in staging only |

Fields the API omits on a given row (null) are created as NULL so every day's
staging table has the same 35 columns. See `src/schema.py`.
