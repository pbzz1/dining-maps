select
    menu_item_id,
    score,
    absolute_grade,
    relative_grade,
    percentile,
    basis
from {{ source('public', 'diet_score') }}
