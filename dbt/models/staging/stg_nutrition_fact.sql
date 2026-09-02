select
    id as nutrition_fact_id,
    menu_item_id,
    nutrient_name,
    value,
    unit
from {{ source('public', 'nutrition_fact') }}
