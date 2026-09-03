select
    menu_item_id,
    score,
    absolute_grade,
    relative_grade,
    percentile,
    basis
from {{ ref('stg_diet_score') }}
