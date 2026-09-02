select
    id as check_id,
    run_id,
    check_name,
    scope,
    severity,
    detail
from {{ source('public', 'data_quality_check') }}
