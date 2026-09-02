select
    store_id,
    restaurant_id,
    branch_name,
    address,
    lat,
    lng,
    last_seen_at
from {{ ref('stg_store') }}
