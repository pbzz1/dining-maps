# -*- coding: utf-8 -*-
"""GA4 유저 행동 로그 분석.

사전 준비 (1회):
  1. pip install google-analytics-data google-auth-oauthlib
  2. GA4 관리 > 속성 설정에서 숫자 속성 ID 확인 (G-B8QRKP6DTW 가 붙은 속성)
  3. gcloud CLI 설치 후: gcloud auth application-default login
     (본인 구글 계정으로 로그인 -- 이미 GA4 속성의 소유자/편집자이므로 별도 권한 추가 불필요)

실행:
  python scripts/analytics/analyze_ga4_events.py --property-id 123456789 [--days 30]

출력: docs/ga4_report.md
"""
import argparse
from datetime import date

from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    DateRange, Dimension, Metric, RunReportRequest,
)


def run(client, prop, dims, mets, days, limit=50):
    req = RunReportRequest(
        property=f"properties/{prop}",
        dimensions=[Dimension(name=d) for d in dims],
        metrics=[Metric(name=m) for m in mets],
        date_ranges=[DateRange(start_date=f"{days}daysAgo", end_date="today")],
        limit=limit,
    )
    resp = client.run_report(req)
    return [
        [v.value for v in row.dimension_values] + [v.value for v in row.metric_values]
        for row in resp.rows
    ]


def md_table(headers, rows):
    lines = ["| " + " | ".join(headers) + " |",
             "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(lines) if rows else "_데이터 없음_"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--property-id", required=True)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--out", default="docs/ga4_report.md")
    a = ap.parse_args()

    client = BetaAnalyticsDataClient()  # gcloud ADC 로그인 자격증명 자동 사용
    p, d = a.property_id, a.days

    sections = [
        ("이벤트별 발생 수 (어떤 기능이 쓰이나)",
         ["eventName"], ["eventCount", "totalUsers"]),
        ("일별 활성 사용자 추이",
         ["date"], ["activeUsers", "screenPageViews"]),
        ("시간대별 사용 패턴",
         ["hour"], ["activeUsers", "eventCount"]),
        ("요일별 사용 패턴",
         ["dayOfWeekName"], ["activeUsers", "eventCount"]),
        ("페이지별 조회",
         ["pagePath"], ["screenPageViews", "totalUsers"]),
        ("신규 vs 재방문",
         ["newVsReturning"], ["totalUsers", "sessions"]),
        ("유입 채널",
         ["sessionDefaultChannelGroup"], ["sessions", "totalUsers"]),
        ("지역 (도시)",
         ["city"], ["totalUsers", "sessions"]),
        ("기기 유형",
         ["deviceCategory"], ["totalUsers"]),
        ("OS / 브라우저",
         ["operatingSystem", "browser"], ["totalUsers"]),
        ("참여도 지표",
         ["sessionDefaultChannelGroup"],
         ["engagementRate", "averageSessionDuration", "screenPageViewsPerSession"]),
    ]

    # 이벤트 파라미터(view, name 등)는 GA4 맞춤 측정기준으로 등록해야 customEvent: 로 조회 가능.
    # register_ga4_custom_dimensions.py 로 먼저 등록해두면 아래 섹션이 채워짐.
    custom_sections = [
        ("어떤 매장/브랜드를 많이 클릭했나", ["customEvent:name"], ["eventCount"]),
        ("지도 검색 키워드", ["customEvent:keyword"], ["eventCount"]),
        ("어느 뷰(지도/대시보드/신메뉴)에 머무나", ["customEvent:view"], ["eventCount"]),
        ("등급 필터 사용", ["customEvent:grade"], ["eventCount"]),
        ("정렬 기준 선호", ["customEvent:sort"], ["eventCount"]),
        ("대시보드 영양소 탭", ["customEvent:nutrient"], ["eventCount"]),
        ("신메뉴 유튜브 리뷰 검색", ["customEvent:menu"], ["eventCount"]),
    ]

    out = [f"# GA4 유저 행동 리포트 ({d}일, {date.today()} 기준)\n"]
    for title, dims, mets in sections:
        rows = run(client, p, dims, mets, d)
        if dims in (["date"], ["hour"]):
            rows.sort()
        out.append(f"## {title}\n\n{md_table(dims + mets, rows)}\n")

    for title, dims, mets in custom_sections:
        try:
            rows = run(client, p, dims, mets, d)
        except Exception as e:
            out.append(f"## {title}\n\n_맞춤 측정기준 미등록 또는 조회 실패: {e}_\n")
            continue
        out.append(f"## {title}\n\n{md_table(dims + mets, rows)}\n")

    with open(a.out, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"리포트 저장: {a.out}")


if __name__ == "__main__":
    main()
