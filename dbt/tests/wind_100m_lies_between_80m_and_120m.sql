-- 100 m is undocumented, so check it against the documented heights around it.
{{ config(severity='warn') }}
select 
location_id, 
valid_at_utc, 
wind_speed_80m_ms, 
wind_speed_100m_ms, 
wind_speed_120m_ms
from {{ ref('silver_hourly_weather') }}
where wind_speed_100m_ms < least(wind_speed_80m_ms, wind_speed_120m_ms) - 0.1
    or wind_speed_100m_ms > greatest(wind_speed_80m_ms, wind_speed_120m_ms) + 0.1
