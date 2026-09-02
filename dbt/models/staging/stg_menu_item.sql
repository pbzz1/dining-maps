select
    id            as menu_item_id,
    restaurant_id,
    name          as menu_item_name,
    category,
    category_group,
    price_krw,
    weight_g,
    nutrition_basis,
    allergy_info,
    origin_info,
    data_source,
    released_at,
    image_url,
    youtube_video_id
from {{ source('public', 'menu_item') }}
