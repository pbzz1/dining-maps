-- 크롤 회차별 브랜드 x 영양소 평균. append-only 스냅샷이 원천이라
-- "언제부터 나트륨이 올랐나"를 답할 수 있는 유일한 테이블이다.
select cr.run_id                        as run_id,
       cr.started_at                    as started_at,
       ms.restaurant_name               as restaurant_name,
       ns.nutrient_name                 as nutrient_name,
       ns.unit                          as unit,
       round(avg(ns.value)::numeric, 1) as avg_value,
       count(*)                         as item_count
from {{ ref('stg_crawl_run') }} cr
join {{ ref('stg_menu_snapshot') }} ms      on ms.run_id = cr.run_id
join {{ ref('stg_nutrition_snapshot') }} ns on ns.menu_snapshot_id = ms.menu_snapshot_id
where cr.status = 'passed'
group by 1, 2, 3, 4, 5
