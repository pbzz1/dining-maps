select
    id as menu_snapshot_id,
    run_id,
    restaurant_name,
    menu_name,
    category,
    price_krw,
    weight_g
from {{ source('public', 'menu_snapshot') }}
