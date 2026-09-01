# -*- coding: utf-8 -*-
"""track()이 보내는 이벤트 파라미터를 GA4 맞춤 측정기준으로 등록.

등록 시점 이후 이벤트부터 analyze_ga4_events.py 의 customEvent: 섹션에서 조회 가능.
(GA4는 소급 적용이 안 되므로 가능한 한 빨리 실행할 것)

사전 준비: pip install google-analytics-admin google-auth-oauthlib
  gcloud auth application-default login  (본인 구글 계정, GA4 속성의 편집자 이상 권한 필요)

실행:
  python scripts/analytics/register_ga4_custom_dimensions.py --property-id 123456789
"""
import argparse

from google.analytics.admin_v1beta import (
    AnalyticsAdminServiceClient, CustomDimension, CreateCustomDimensionRequest,
)

# track()이 실제로 보내는 이벤트 파라미터들 (frontend-react/src 전수 조사 기준)
PARAMS = [
    ("name", "매장/브랜드명 (select_restaurant, map_store_focus)"),
    ("keyword", "지도 검색어 (map_search)"),
    ("view", "현재 뷰: map/dashboard/new-menu (view_change, scroll_depth)"),
    ("grade", "선택한 등급 필터 (map_grade_filter)"),
    ("type", "등급 표시 방식 (map_grade_type)"),
    ("mode", "등급 모드: relative/absolute (list_grade_mode)"),
    ("sort", "메뉴 정렬 기준 (menu_sort)"),
    ("key", "신메뉴 정렬 키 (new_menu_sort)"),
    ("nutrient", "대시보드 영양소 탭 (dashboard_nutrient_tab)"),
    ("menu", "유튜브 리뷰 검색한 신메뉴명 (youtube_review_search)"),
    ("percent", "스크롤 깊이 % (scroll_depth)"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--property-id", required=True)
    a = ap.parse_args()

    client = AnalyticsAdminServiceClient()  # gcloud ADC 로그인 자격증명 자동 사용
    parent = f"properties/{a.property_id}"

    existing = {
        cd.parameter_name
        for cd in client.list_custom_dimensions(parent=parent)
    }

    for param_name, desc in PARAMS:
        if param_name in existing:
            print(f"skip (이미 등록됨): {param_name}")
            continue
        client.create_custom_dimension(
            CreateCustomDimensionRequest(
                parent=parent,
                custom_dimension=CustomDimension(
                    parameter_name=param_name,
                    display_name=param_name,
                    description=desc,
                    scope=CustomDimension.DimensionScope.EVENT,
                ),
            )
        )
        print(f"등록 완료: {param_name} ({desc})")

    print("\n완료. GA4는 최대 속성당 50개까지 맞춤 측정기준을 허용하며, 지금부터 쌓이는 데이터부터 조회 가능.")


if __name__ == "__main__":
    main()
