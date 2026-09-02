select
    menu_item_id,
    nutrient_name,
    value,
    unit
from {{ ref('stg_nutrition_fact') }}
