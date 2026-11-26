-- Catches clock errors: the hour ending at valid_at lies wholly in the dark, yet has sun.
-- The API's own noise at night is about 1 W/m2, hence the tolerance.
select h.location_id, h.valid_at_local, h.ghi_wm2, d.sunrise_local, d.sunset_local
from {{ ref('silver_hourly_weather') }} as h
inner join {{ ref('silver_daily_weather') }} as d using (location_id, local_date)
where (h.valid_at_local <= d.sunrise_local or h.valid_at_local - interval 1 hour >= d.sunset_local)
    and h.ghi_wm2 > 5
