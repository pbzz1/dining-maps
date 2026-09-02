select
    id as nutrition_snapshot_id,
    menu_snapshot_id,
    nutrient_name,
    value,
    unit
from {{ source('public', 'nutrition_snapshot') }}
