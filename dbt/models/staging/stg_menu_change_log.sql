select
    id as change_log_id,
    run_id,
    restaurant_name,
    menu_name,
    change_type,
    field_name,
    old_value,
    new_value,
    pct_change,
    verdict
from {{ source('public', 'menu_change_log') }}
