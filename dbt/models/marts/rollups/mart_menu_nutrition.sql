-- 메뉴 1행 = 1레코드인 wide 팩트 테이블. BI 도구(Tableau)가 직접 썰어 쓰는 단일 소스다.
-- 기존 mart_*는 이미 집계된 요약이라 잘라볼 여지가 없고, fact_nutrition은 long 포맷이라
-- BI에서 다루기 번거롭다 -- 그 둘 사이를 메우는 게 이 모델의 존재 이유.
--
-- 값의 기준(nutrition_basis)이 행마다 다른 게 이 도메인의 핵심 함정이다:
--   per_serving(NULL이 이 뜻, 3,820행) / per_serving 명시(533) / per_100g(159) / per_total(20)
-- per_100g 브랜드(BHC·교촌)는 영양소가 100g당인데 weight_g는 제품 전체 중량이라 둘을 나누면
-- 에러 없이 틀린 수가 나온다. per_total(뚜레쥬르 6호 케이크 8,690kcal 등)은 분자가 제품
-- 전체 기준이라 1인분 메뉴와 같은 축에 못 올린다.
--
-- 그래서 파생값(kcal_per_g, brand_pct_*)은 per_serving 행에만 채우고 나머지는 NULL로 둔다.
-- 틀린 값을 채우는 것보다 비는 게 낫고, nutrition_basis를 그대로 실어 보내 BI에서 필터로
-- 쓰게 한다. 선례: app/menus/router.py:33-39(per_100g 제외), app/new_menu/router.py:150-168(환산).
with nut as (
    select menu_item_id,
           max(value) filter (where nutrient_name = 'calorie')        as calorie_kcal,
           max(value) filter (where nutrient_name = 'protein')        as protein_g,
           max(value) filter (where nutrient_name = 'sugar')          as sugar_g,
           max(value) filter (where nutrient_name = 'saturated_fat')  as saturated_fat_g,
           max(value) filter (where nutrient_name = 'sodium')         as sodium_mg
    from {{ ref('fact_nutrition') }}
    group by 1
), base as (
    select mi.menu_item_id,
           mi.restaurant_id,
           r.restaurant_name,
           mi.menu_item_name,
           mi.category,
           mi.category_group,
           mi.price_krw,
           mi.weight_g,
           -- db/schema.sql상 NULL은 per_serving을 뜻한다. 아래 파생값 조건과 BI 필터가
           -- NULL을 따로 다루지 않아도 되게 여기서 한 번만 편다.
           coalesce(mi.nutrition_basis, 'per_serving') as nutrition_basis,
           mi.released_at,
           n.calorie_kcal,
           n.protein_g,
           n.sugar_g,
           n.saturated_fat_g,
           n.sodium_mg,
           fd.score           as diet_score,
           fd.absolute_grade,
           fd.relative_grade,
           -- fact_diet_score.percentile은 전체 메뉴 기준이다. 아래 brand_pct_*(브랜드 내
           -- 기준)와 헷갈리지 않게 이름을 구분해 싣는다.
           fd.percentile      as diet_percentile
    from {{ ref('dim_menu_item') }} mi
    join {{ ref('dim_restaurant') }} r on r.restaurant_id = mi.restaurant_id
    left join nut n on n.menu_item_id = mi.menu_item_id
    left join {{ ref('fact_diet_score') }} fd on fd.menu_item_id = mi.menu_item_id
)
select b.menu_item_id,
       b.restaurant_id,
       b.restaurant_name,
       b.menu_item_name,
       b.category,
       b.category_group,
       b.price_krw,
       b.weight_g,
       b.nutrition_basis,
       b.released_at,
       b.calorie_kcal,
       b.protein_g,
       b.sugar_g,
       b.saturated_fat_g,
       b.sodium_mg,
       b.diet_score,
       b.absolute_grade,
       b.relative_grade,
       b.diet_percentile,
       -- 에너지 밀도(g당 kcal). per_serving에서만 분자와 분모의 기준이 맞고, 중량 미공개
       -- 메뉴를 0으로 두면 전부 꼴찌로 붙어 순위가 거짓말이 되므로 아예 비운다.
       -- (menus/router.py의 비율 정렬이 쓰는 MIN_CALORIE 하한은 여기 안 넣었다 -- 그 하한은
       --  분모가 반올림된 g 단위 영양소일 때 필요한 것이고, 여기 분모는 중량이라 해당 없다.)
       case when b.nutrition_basis = 'per_serving' and b.weight_g > 0
            then round((b.calorie_kcal / b.weight_g)::numeric, 3)
       end as kcal_per_g,
       -- 브랜드 내 백분위(0=최저, 1=최고). partition에 nutrition_basis를 넣는 이유: 기준이
       -- 한 브랜드 안에서 섞인 곳이 실제로 있다(교촌치킨 per_100g+per_serving, 도미노피자
       -- per_serving+per_total). 브랜드만으로 자르면 기준이 다른 값끼리 줄을 세우게 된다.
       -- "값이 NULL인가"까지 넣는 이유: percent_rank는 NULL 행도 세어 분모를 키운다.
       -- NULL을 별도 파티션으로 격리해야 값 있는 행끼리만 순위가 매겨지고, 격리된 쪽과
       -- per_serving이 아닌 쪽은 아래 case로 비운다.
       case when b.nutrition_basis = 'per_serving' and b.calorie_kcal is not null
            then round(percent_rank() over (partition by b.restaurant_id, b.nutrition_basis,
                 (b.calorie_kcal is null) order by b.calorie_kcal)::numeric, 3)
       end as brand_pct_calorie,
       case when b.nutrition_basis = 'per_serving' and b.protein_g is not null
            then round(percent_rank() over (partition by b.restaurant_id, b.nutrition_basis,
                 (b.protein_g is null) order by b.protein_g)::numeric, 3)
       end as brand_pct_protein,
       case when b.nutrition_basis = 'per_serving' and b.sugar_g is not null
            then round(percent_rank() over (partition by b.restaurant_id, b.nutrition_basis,
                 (b.sugar_g is null) order by b.sugar_g)::numeric, 3)
       end as brand_pct_sugar,
       case when b.nutrition_basis = 'per_serving' and b.saturated_fat_g is not null
            then round(percent_rank() over (partition by b.restaurant_id, b.nutrition_basis,
                 (b.saturated_fat_g is null) order by b.saturated_fat_g)::numeric, 3)
       end as brand_pct_saturated_fat,
       case when b.nutrition_basis = 'per_serving' and b.sodium_mg is not null
            then round(percent_rank() over (partition by b.restaurant_id, b.nutrition_basis,
                 (b.sodium_mg is null) order by b.sodium_mg)::numeric, 3)
       end as brand_pct_sodium,
       -- 백분위를 계산한 모집단 크기. 1이면 percent_rank가 늘 0이라 순위에 의미가 없다 --
       -- BI에서 이 값으로 걸러 쓰라고 같이 싣는다.
       count(*) over (partition by b.restaurant_id, b.nutrition_basis) as brand_peer_count
from base b
