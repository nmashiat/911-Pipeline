"""
The schema we *expect*, declared explicitly.

Why: the API omits null fields per row, so the set of keys varies row to row.
If we let pandas infer columns from the data, a day where no unit reached
hospital would produce a table with no hospital_dttm column. Declaring the
schema here means every day's table has the same shape.
"""

# Columns that uniquely identify a row: one unit's response to one call.
KEY_COLUMNS = ["rowid"]

# Every timestamp column. Parsed to datetime; missing is allowed except received_dttm.
TIMESTAMP_COLUMNS = [
    "received_dttm",
    "entry_dttm",
    "dispatch_dttm",
    "response_dttm",
    "on_scene_dttm",
    "transport_dttm",
    "hospital_dttm",
    "available_dttm",
    "data_as_of",
    "data_loaded_at",
]

DATE_COLUMNS = ["call_date", "watch_date"]

INT_COLUMNS = ["number_of_alarms", "unit_sequence_in_call_dispatch"]

BOOL_COLUMNS = ["als_unit"]

# Everything else stays as text. Priorities are text because SF uses letters too.
TEXT_COLUMNS = [
    "call_number",
    "incident_number",
    "unit_id",
    "unit_type",
    "call_type",
    "call_type_group",
    "call_final_disposition",
    "original_priority",
    "priority",
    "final_priority",
    "address",
    "city",
    "zipcode_of_incident",
    "battalion",
    "station_area",
    "box",
    "fire_prevention_district",
    "supervisor_district",
    "neighborhoods_analysis_boundaries",
]

# case_location is a GeoJSON point; we flatten it into these two.
GEO_SOURCE = "case_location"
GEO_COLUMNS = ["longitude", "latitude"]

ALL_COLUMNS = (
    KEY_COLUMNS
    + TEXT_COLUMNS
    + TIMESTAMP_COLUMNS
    + DATE_COLUMNS
    + INT_COLUMNS
    + BOOL_COLUMNS
    + GEO_COLUMNS
)

# Rows missing any of these are rejected, not loaded.
REQUIRED_COLUMNS = ["rowid", "call_number", "unit_id", "received_dttm"]
