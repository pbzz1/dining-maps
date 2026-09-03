select
    menu_item_id,
    restaurant_id,
    menu_item_name,
    category,
    category_group,
    price_krw,
    weight_g,
    nutrition_basis,
    data_source,
    released_at
from {{ ref('stg_menu_item') }}
