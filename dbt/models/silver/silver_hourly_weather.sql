-- Typed hourly rows. The newest forecast wins for each location and hour.
with exploded as (
    select
        run_id,
        location_id,
        retrieved_at,
        {{ unnest_json('hourly', 'time', 'BIGINT') }}                  as valid_epoch,
        {{ unnest_json('hourly', 'temperature_2m') }}                  as temperature_2m_c,
        {{ unnest_json('hourly', 'surface_pressure') }}                as surface_pressure_hpa,
        {{ unnest_json('hourly', 'cloud_cover') }}                     as cloud_cover_pct,
        {{ unnest_json('hourly', 'shortwave_radiation') }}             as ghi_wm2,
        {{ unnest_json('hourly', 'direct_normal_irradiance') }}        as dni_wm2,
        {{ unnest_json('hourly', 'diffuse_radiation') }}               as dhi_wm2,
        {{ unnest_json('hourly', 'global_tilted_irradiance') }}        as gti_wm2,
        {{ unnest_json('hourly', 'wind_speed_10m') }}                  as wind_speed_10m_ms,
        {{ unnest_json('hourly', 'wind_speed_80m') }}                  as wind_speed_80m_ms,
        {{ unnest_json('hourly', 'wind_speed_100m') }}                 as wind_speed_100m_ms,
        {{ unnest_json('hourly', 'wind_speed_120m') }}                 as wind_speed_120m_ms,
        {{ unnest_json('hourly', 'wind_speed_200m') }}                 as wind_speed_200m_ms,
        {{ unnest_json('hourly', 'wind_direction_100m') }}             as wind_direction_100m_deg,
        {{ unnest_json('hourly', 'wind_gusts_10m') }}                  as wind_gusts_10m_ms
    from {{ source('bronze', 'raw_open_meteo') }}
    where endpoint = 'hourly'
),

deduplicated as (
    select *
    from exploded
    -- hours past the end of the forecast come back empty and must not win
    where coalesce(temperature_2m_c, ghi_wm2, gti_wm2, wind_speed_100m_ms) is not null
    qualify row_number() over (
        partition by location_id, valid_epoch
        order by retrieved_at desc, run_id desc
    ) = 1
)

select
    d.location_id,
    to_timestamp(d.valid_epoch) at time zone 'UTC'                     as valid_at_utc,
    to_timestamp(d.valid_epoch) at time zone l.timezone                as valid_at_local,
    cast(to_timestamp(d.valid_epoch) at time zone l.timezone as date)  as local_date,
    cast(d.retrieved_at at time zone l.timezone as date)               as issued_local_date,
    d.* exclude (location_id, valid_epoch)
        replace (
            -- the model emits stray values of -1 W/m2 at night; anything lower is left
            -- for the range test to reject
            case when d.ghi_wm2 between -5 and 0 then 0 else d.ghi_wm2 end as ghi_wm2,
            case when d.gti_wm2 between -5 and 0 then 0 else d.gti_wm2 end as gti_wm2
        ),
    coalesce(d.ghi_wm2 between -5 and -0.001, false)
        or coalesce(d.gti_wm2 between -5 and -0.001, false)            as is_radiation_clamped
from deduplicated as d
inner join {{ ref('locations') }} as l using (location_id)
