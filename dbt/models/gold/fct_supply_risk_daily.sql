-- Renewable supply risk, 0 (strong sun and wind) to 100 (dark, calm and gusty).
-- Weights and references are vars in dbt_project.yml.
with parts as (
    select
        location_id,
        local_date,
        lead_days,
        forecast_confidence,
        pv_yield_kwh_kwp,
        wind_cf_100m,
        wind_gust_max_ms,
        1 - least(1, pv_yield_kwh_kwp / {{ var('risk_pv_reference') }})        as solar_shortfall,
        1 - least(1, wind_cf_100m / {{ var('risk_wind_cf_reference') }})       as wind_shortfall,
        least(1, greatest(0, (wind_gust_max_ms - {{ var('risk_gust_floor') }})
            / ({{ var('risk_gust_ceiling') }} - {{ var('risk_gust_floor') }}))) as gust_hazard
    from {{ ref('fct_energy_daily') }}
    where is_complete
),

scored as (
    select
        *,
        -- whole points, so a displayed score always agrees with its band
        cast(round({{ var('risk_weight_solar') }} * solar_shortfall
            + {{ var('risk_weight_wind') }} * wind_shortfall
            + {{ var('risk_weight_gust') }} * gust_hazard) as integer)         as supply_risk_score
    from parts
)

select
    *,
    case
        when supply_risk_score >= {{ var('risk_band_high') }} then 'high'
        when supply_risk_score >= {{ var('risk_band_moderate') }} then 'moderate'
        else 'low'
    end                                                                        as risk_band
from scored
