{# 커스텀 스키마를 target 스키마 뒤에 이어붙이는 dbt 기본 동작을 끈다.
   rollups 모델이 db/schema.sql이 쓰던 public.mart_* 이름을 그대로 써야
   app/stats/router.py의 unqualified SELECT가 안 깨지기 때문. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
