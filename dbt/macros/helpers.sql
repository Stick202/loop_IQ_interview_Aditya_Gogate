{# Use schema names as written (silver, gold), not main_silver / main_gold. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ (custom_schema_name or target.schema) | trim }}
{%- endmacro %}

{# Unnest one JSON array from the raw payload. Arrays in a block share one length
   (checked at ingestion), so several of these in one select stay row-aligned. #}
{% macro unnest_json(block, variable, type='DOUBLE') -%}
    unnest(from_json(payload -> '$.{{ block }}.{{ variable }}', '["{{ type }}"]'))
{%- endmacro %}

{# Generic turbine capacity factor, 0 to 1. Speed is density-corrected (IEC 61400-12). #}
{% macro capacity_factor(speed, air_density) -%}
    case
        when {{ speed }} is null or {{ air_density }} is null then null
        when {{ speed }} >= {{ var('wind_cut_out') }} then 0.0
        when {{ speed }} * cbrt({{ air_density }} / 1.225) < {{ var('wind_cut_in') }} then 0.0
        when {{ speed }} * cbrt({{ air_density }} / 1.225) >= {{ var('wind_rated') }} then 1.0
        else (pow({{ speed }}, 3) * {{ air_density }} / 1.225 - pow({{ var('wind_cut_in') }}, 3))
             / (pow({{ var('wind_rated') }}, 3) - pow({{ var('wind_cut_in') }}, 3))
    end
{%- endmacro %}
