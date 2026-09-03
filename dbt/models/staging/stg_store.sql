select
    id as store_id,
    restaurant_id,
    branch_name,
    address,
    lat,
    lng,
    kakao_place_id,
    last_seen_at
from {{ source('public', 'store') }}
