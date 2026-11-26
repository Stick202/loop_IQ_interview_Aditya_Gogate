-- One row per city over a shared window: dates from today onward that are complete for
-- every city. Without this, cities would be ranked over different days.
with latest_issue as (
    select max(issued_local_date) as issued_date from {{ ref('fct_energy_hourly') }}
),

shared_days as (
    select f.local_date, bool_and(f.is_complete_200m) as has_200m
    from {{ ref('fct_energy_daily') }} as f
    cross join latest_issue as i
    where f.is_complete and f.local_date >= i.issued_date
    group by f.local_date
    having count(*) = (select count(*) from {{ ref('dim_location') }})
)

select
    l.location_id,
    l.city,
    l.country,
    l.panel_tilt_deg,
    min(f.local_date)                                                     as window_start,
    max(f.local_date)                                                     as window_end,
    count(*)                                                              as days,
    avg(f.ghi_kwh_m2)                                                     as ghi_kwh_m2_day,
    avg(f.gti_kwh_m2)                                                     as gti_kwh_m2_day,
    avg(f.pv_yield_kwh_kwp)                                               as pv_yield_kwh_kwp_day,
    avg(f.wind_speed_100m_ms)                                             as wind_speed_100m_ms,
    avg(f.wind_power_density_100m_wm2)                                    as wind_power_density_100m_wm2,
    avg(f.wind_cf_100m)                                                   as wind_cf_100m,
    -- 200 m ends earlier, so the height comparison uses its own matched days
    count(*) filter (where s.has_200m)                                    as days_200m,
    avg(f.wind_cf_100m) filter (where s.has_200m)                         as wind_cf_100m_matched,
    avg(f.wind_cf_200m) filter (where s.has_200m)                         as wind_cf_200m_matched,
    avg(f.wind_power_density_100m_wm2) filter (where s.has_200m)          as wind_power_density_100m_matched_wm2,
    avg(f.wind_power_density_200m_wm2) filter (where s.has_200m)          as wind_power_density_200m_matched_wm2,
    avg(r.supply_risk_score)                                              as supply_risk_score_avg,
    max(r.supply_risk_score)                                              as supply_risk_score_max,
    arg_max(f.local_date, r.supply_risk_score)                            as highest_risk_date,
    count(*) filter (where r.risk_band = 'high')                          as high_risk_days
from {{ ref('fct_energy_daily') }} as f
inner join shared_days as s using (local_date)
inner join {{ ref('fct_supply_risk_daily') }} as r using (location_id, local_date)
inner join {{ ref('dim_location') }} as l using (location_id)
group by l.location_id, l.city, l.country, l.panel_tilt_deg
