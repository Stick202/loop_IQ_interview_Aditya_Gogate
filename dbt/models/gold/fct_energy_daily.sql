-- Daily facts. Totals are null unless every hour of the local day is present, so a
-- partial first or last day can never look like a low-yield one.
with hourly as (
    select
        location_id,
        local_date,
        max(issued_local_date)              as issued_local_date,
        count(*)                            as hours_present,
        count(pv_yield_kwh_kwp)             as solar_hours,
        count(wind_cf_100m)                 as wind_100m_hours,
        count(wind_cf_200m)                 as wind_200m_hours,
        sum(ghi_wm2) / 1000                 as ghi_kwh_m2,
        sum(gti_wm2) / 1000                 as gti_kwh_m2,
        sum(pv_yield_kwh_kwp)               as pv_yield_kwh_kwp,
        avg(wind_speed_100m_ms)             as wind_speed_100m_ms,
        avg(wind_speed_200m_ms)             as wind_speed_200m_ms,
        avg(wind_power_density_100m_wm2)    as wind_power_density_100m_wm2,
        avg(wind_power_density_200m_wm2)    as wind_power_density_200m_wm2,
        avg(wind_cf_100m)                   as wind_cf_100m,
        avg(wind_cf_200m)                   as wind_cf_200m,
        max(wind_gusts_10m_ms)              as wind_gust_max_ms,
        avg(cloud_cover_pct)                as cloud_cover_pct
    from {{ ref('fct_energy_hourly') }}
    group by location_id, local_date
),

with_expected as (
    select
        h.*,
        -- 24 except on daylight-saving change days (23 or 25)
        cast((epoch(cast(h.local_date + interval 1 day as timestamp) at time zone l.timezone)
            - epoch(cast(h.local_date as timestamp) at time zone l.timezone)) / 3600 as integer) as hours_expected
    from hourly as h
    inner join {{ ref('dim_location') }} as l using (location_id)
),

flagged as (
    select
        *,
        solar_hours = hours_expected and wind_100m_hours = hours_expected  as is_complete,
        wind_200m_hours = hours_expected                                   as is_complete_200m
    from with_expected
)

select
    f.location_id,
    f.local_date,
    f.local_date - f.issued_local_date                                     as lead_days,
    case
        when f.local_date - f.issued_local_date <= 6 then 'high'
        when f.local_date - f.issued_local_date <= 10 then 'medium'
        else 'low'
    end                                                                    as forecast_confidence,
    f.is_complete,
    f.is_complete_200m,
    f.hours_present,
    f.hours_expected,
    f.wind_200m_hours,
    case when f.is_complete then f.ghi_kwh_m2 end                          as ghi_kwh_m2,
    case when f.is_complete then f.gti_kwh_m2 end                          as gti_kwh_m2,
    case when f.is_complete then f.pv_yield_kwh_kwp end                    as pv_yield_kwh_kwp,
    case when f.is_complete then f.wind_speed_100m_ms end                  as wind_speed_100m_ms,
    case when f.is_complete then f.wind_power_density_100m_wm2 end         as wind_power_density_100m_wm2,
    case when f.is_complete then f.wind_cf_100m end                        as wind_cf_100m,
    case when f.is_complete then f.wind_cf_100m * f.hours_expected end     as wind_yield_100m_kwh_kw,
    case when f.is_complete_200m then f.wind_speed_200m_ms end             as wind_speed_200m_ms,
    case when f.is_complete_200m then f.wind_power_density_200m_wm2 end    as wind_power_density_200m_wm2,
    case when f.is_complete_200m then f.wind_cf_200m end                   as wind_cf_200m,
    case when f.is_complete_200m then f.wind_cf_200m * f.hours_expected end as wind_yield_200m_kwh_kw,
    case when f.is_complete then f.wind_gust_max_ms end                    as wind_gust_max_ms,
    case when f.is_complete then f.cloud_cover_pct end                     as cloud_cover_pct,
    d.temperature_max_c,
    d.temperature_min_c,
    d.sunrise_local,
    d.sunset_local,
    d.daylight_hours,
    d.sunshine_hours,
    d.ghi_kwh_m2                                                           as api_ghi_kwh_m2
from flagged as f
left join {{ ref('silver_daily_weather') }} as d using (location_id, local_date)
