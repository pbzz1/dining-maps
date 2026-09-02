-- 크롤 회차별 품질 요약: 검증 pass/warn/fail 수, 감지된 변경 건수.
-- "파이프라인이 스스로를 감시하고 있다"를 보여주는 화면의 원천.
select cr.run_id      as run_id,
       cr.started_at  as started_at,
       cr.source      as source,
       cr.status      as status,
       count(dqc.check_id)                                as checks_total,
       count(*) filter (where dqc.severity = 'pass')       as checks_pass,
       count(*) filter (where dqc.severity = 'warn')       as checks_warn,
       count(*) filter (where dqc.severity = 'fail')       as checks_fail,
       (select count(*) from {{ ref('stg_menu_change_log') }} m
         where m.run_id = cr.run_id and m.verdict = 'real_change')          as real_changes,
       (select count(*) from {{ ref('stg_menu_change_log') }} m
         where m.run_id = cr.run_id and m.verdict = 'suspected_parser_bug') as suspected_parser_bugs
from {{ ref('stg_crawl_run') }} cr
left join {{ ref('stg_data_quality_check') }} dqc on dqc.run_id = cr.run_id
group by cr.run_id, cr.started_at, cr.source, cr.status
