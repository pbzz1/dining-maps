select
    id   as restaurant_id,
    name as restaurant_name
from {{ source('public', 'restaurant') }}
