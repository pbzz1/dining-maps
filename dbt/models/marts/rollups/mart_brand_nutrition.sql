-- 브랜드별 요약: 메뉴/매장 수, 평균 점수, 등급 분포, 주요 영양소 평균.
-- avg가 조인 곱으로 왜곡되지 않도록 영양소/등급을 각자 집계한 뒤 붙인다.
-- (db/schema.sql의 옛 mart_brand_nutrition 매트뷰를 그대로 옮긴 것 -- app/stats/router.py가
-- public.mart_brand_nutrition 이름으로 그대로 읽으므로 이름·컬럼을 바꾸면 안 된다.)
with nut as (
    select mi.restaurant_id, fn.nutrient_name, avg(fn.value) as avg_value
    from {{ ref('fact_nutrition') }} fn
    join {{ ref('dim_menu_item') }} mi on mi.menu_item_id = fn.menu_item_id
    group by 1, 2
), grades as (
    select mi.restaurant_id,
           count(*)                                          as scored_count,
           avg(fd.score)                                     as avg_score,
           count(*) filter (where fd.absolute_grade = 'A')   as grade_a,
           count(*) filter (where fd.absolute_grade = 'B')   as grade_b,
           count(*) filter (where fd.absolute_grade = 'C')   as grade_c,
           count(*) filter (where fd.absolute_grade = 'D')   as grade_d
    from {{ ref('fact_diet_score') }} fd
    join {{ ref('dim_menu_item') }} mi on mi.menu_item_id = fd.menu_item_id
    group by 1
)
select r.restaurant_id                                                                as restaurant_id,
       r.restaurant_name                                                              as restaurant_name,
       (select count(*) from {{ ref('dim_menu_item') }} mi
         where mi.restaurant_id = r.restaurant_id)                                    as menu_count,
       (select count(*) from {{ ref('dim_store') }} s
         where s.restaurant_id = r.restaurant_id)                                     as store_count,
       coalesce(g.scored_count, 0)         as scored_count,
       round(g.avg_score::numeric, 1)      as avg_score,
       coalesce(g.grade_a, 0) as grade_a,
       coalesce(g.grade_b, 0) as grade_b,
       coalesce(g.grade_c, 0) as grade_c,
       coalesce(g.grade_d, 0) as grade_d,
       round(max(n.avg_value) filter (where n.nutrient_name = 'calorie')::numeric, 0) as avg_calorie_kcal,
       round(max(n.avg_value) filter (where n.nutrient_name = 'sodium')::numeric, 0)  as avg_sodium_mg,
       round(max(n.avg_value) filter (where n.nutrient_name = 'sugar')::numeric, 1)   as avg_sugar_g,
       round(max(n.avg_value) filter (where n.nutrient_name = 'protein')::numeric, 1) as avg_protein_g
from {{ ref('dim_restaurant') }} r
left join grades g on g.restaurant_id = r.restaurant_id
left join nut n    on n.restaurant_id = r.restaurant_id
group by r.restaurant_id, r.restaurant_name, g.scored_count, g.avg_score,
         g.grade_a, g.grade_b, g.grade_c, g.grade_d
