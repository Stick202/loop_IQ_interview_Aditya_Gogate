-- Hourly energy potential, per kWp of panel and per kW of turbine.
with physics as (
    select
        *,
        -- dry air at the surface; about 1% too dense at hub height
        surface_pressure_hpa * 100 / (287.05 * (temperature_2m_c + 273.15))    as air_density_kg_m3,
        temperature_2m_c + gti_wm2 * ({{ var('pv_noct') }} - 20) / 800.0       as pv_cell_temp_c
    from {{ ref('silver_hourly_weather') }}
)

select
    location_id,
    valid_at_utc,
    valid_at_local,
    local_date,
    issued_local_date,
    retrieved_at at time zone 'UTC'                                            as retrieved_at_utc,
    temperature_2m_c,
    cloud_cover_pct,
    ghi_wm2,
    gti_wm2,
    pv_cell_temp_c,
    -- null stays null: greatest() skips nulls and would report a missing hour as zero yield
    case when gti_wm2 is not null then round(greatest(0, gti_wm2 / 1000
        * {{ var('pv_system_efficiency') }}
        * (1 + {{ var('pv_temp_coefficient') }} * (pv_cell_temp_c - 25))), 4)
    end                                                                        as pv_yield_kwh_kwp,
    air_density_kg_m3,
    wind_speed_100m_ms,
    wind_speed_200m_ms,
    wind_gusts_10m_ms,
    0.5 * air_density_kg_m3 * pow(wind_speed_100m_ms, 3)                       as wind_power_density_100m_wm2,
    0.5 * air_density_kg_m3 * pow(wind_speed_200m_ms, 3)                       as wind_power_density_200m_wm2,
    round({{ capacity_factor('wind_speed_100m_ms', 'air_density_kg_m3') }}, 4) as wind_cf_100m,
    round({{ capacity_factor('wind_speed_200m_ms', 'air_density_kg_m3') }}, 4) as wind_cf_200m
from physics
