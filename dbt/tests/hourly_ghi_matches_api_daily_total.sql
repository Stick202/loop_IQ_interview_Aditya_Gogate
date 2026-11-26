-- Our hourly GHI sum must agree with the API's own daily total within 2%.
select location_id, local_date, ghi_kwh_m2, api_ghi_kwh_m2
from {{ ref('fct_energy_daily') }}
where is_complete
    and lead_days >= 0
    and abs(ghi_kwh_m2 - api_ghi_kwh_m2) > 0.02 * api_ghi_kwh_m2
