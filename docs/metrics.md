# Metric definitions

Every number the pipeline produces is defined here. If a definition changes, this
file changes in the same commit.

| Metric | Definition | Table / column |
|---|---|---|
| **Call** | One `call_number`. A call has one or more unit responses. | `fact_call` |
| **Unit response** | One unit dispatched to one call. The source's native grain. | `fact_unit_response` |
| **Response time** | Seconds from `received_dttm` to the **first** unit's `on_scene_dttm` on that call. NULL if no unit reached the scene. | `fact_call.response_secs` |
| **Time to dispatch** | Seconds from `received_dttm` to `dispatch_dttm`, per unit. | `fact_unit_response.secs_to_dispatch` |
| **Dispatch to scene** | Seconds from `dispatch_dttm` to `on_scene_dttm`, per unit. | `fact_unit_response.secs_dispatch_to_scene` |
| **P90 response** | The 90th-percentile `response_secs` within a (date, call type group, neighborhood) cell, nearest-rank method. | `agg_daily.p90_response_secs` |
| **% with on-scene** | Share of calls in a cell where at least one unit has an `on_scene_dttm`. | `agg_daily.pct_calls_with_on_scene` |

## Rules

- Intervals are NULL, never negative, when timestamps are missing or out of order.
  A negative interval would silently pull averages down.
- Rolled-up call timestamps use MIN across units (first received, first dispatched,
  first on scene). "First on scene" is what the public means by response time.
- Priority on `fact_call` is MAX across units (text compare; SF priorities are digits and letters).
- Neighborhood, supervisor district and battalion come from the source's
  `neighborhoods_analysis_boundaries`, `supervisor_district`, `battalion` fields unchanged.
