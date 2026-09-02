select
    restaurant_id,
    restaurant_name
from {{ ref('stg_restaurant') }}
