select
    id as run_id,
    started_at,
    source,
    status
from {{ source('public', 'crawl_run') }}
