-- Typed daily rows as aggregated by the API. The newest forecast wins.
with exploded as (
    select
        run_id,
        location_id,
        retrieved_at,
        cast(payload ->> '$.utc_offset_seconds' as bigint)             as utc_offset_seconds,
        {{ unnest_json('daily', 'time', 'BIGINT') }}                   as day_epoch,
        {{ unnest_json('daily', 'temperature_2m_max') }}               as temperature_max_c,
        {{ unnest_json('daily', 'temperature_2m_min') }}               as temperature_min_c,
        {{ unnest_json('daily', 'sunrise', 'BIGINT') }}                as sunrise_epoch,
        {{ unnest_json('daily', 'sunset', 'BIGINT') }}                 as sunset_epoch,
        {{ unnest_json('daily', 'daylight_duration') }}                as daylight_s,
        {{ unnest_json('daily', 'sunshine_duration') }}                as sunshine_s,
        {{ unnest_json('daily', 'shortwave_radiation_sum') }}          as ghi_mj_m2,
        {{ unnest_json('daily', 'wind_speed_10m_max') }}               as wind_speed_10m_max_ms,
        {{ unnest_json('daily', 'wind_gusts_10m_max') }}               as wind_gusts_10m_max_ms
    from {{ source('bronze', 'raw_open_meteo') }}
    where endpoint = 'daily'
),

dated as (
    select
        *,
        -- the API applies one fixed UTC offset to the whole response
        cast(to_timestamp(day_epoch + utc_offset_seconds) at time zone 'UTC' as date) as local_date
    from exploded
    where temperature_max_c is not null
),

deduplicated as (
    select *
    from dated
    qualify row_number() over (
        partition by location_id, local_date
        order by retrieved_at desc, run_id desc
    ) = 1
)

select
    d.location_id,
    d.local_date,
    d.temperature_max_c,
    d.temperature_min_c,
    to_timestamp(d.sunrise_epoch) at time zone l.timezone              as sunrise_local,
    to_timestamp(d.sunset_epoch) at time zone l.timezone               as sunset_local,
    d.daylight_s / 3600                                                as daylight_hours,
    d.sunshine_s / 3600                                                as sunshine_hours,
    d.ghi_mj_m2 / 3.6                                                  as ghi_kwh_m2,
    d.wind_speed_10m_max_ms,
    d.wind_gusts_10m_max_ms,
    d.run_id,
    d.retrieved_at
from deduplicated as d
inner join {{ ref('locations') }} as l using (location_id)
