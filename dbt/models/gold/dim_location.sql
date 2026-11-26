-- Configured city plus the model grid cell the API actually answered for.
with latest as (
    select location_id, payload
    from {{ source('bronze', 'raw_open_meteo') }}
    where endpoint = 'hourly'
    qualify row_number() over (partition by location_id order by retrieved_at desc) = 1
)

select
    l.location_id,
    l.city,
    l.state_region,
    l.country,
    l.latitude,
    l.longitude,
    cast(b.payload ->> '$.latitude' as double)   as grid_latitude,
    cast(b.payload ->> '$.longitude' as double)  as grid_longitude,
    cast(b.payload ->> '$.elevation' as double)  as elevation_m,
    l.timezone,
    l.panel_tilt_deg,
    l.panel_azimuth_deg
from {{ ref('locations') }} as l
left join latest as b using (location_id)
