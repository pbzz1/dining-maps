"""DAG들이 만들어내는 데이터 자산(Asset) 정의 -- Airflow UI의 Assets 뷰가 이걸로 그려진다.

태스크에 outlets=[...]로 달면 "어떤 태스크가 어떤 테이블을 갱신하는가"가 코드가 아니라
그래프로 남는다. dbt 마트는 두 DAG가 모두 갱신하므로 URI를 여기서 한 번만 정의한다.
"""
from airflow.sdk import Asset

_PG = "postgres://postgres-app:5432/dining_maps/public"

MENU_ITEM = Asset(name="menu_item", uri=f"{_PG}/menu_item")
DIET_SCORE = Asset(name="diet_score", uri=f"{_PG}/diet_score")
STORE = Asset(name="store", uri=f"{_PG}/store")
MARTS = Asset(name="mart_tables", uri=f"{_PG}/mart_brand_nutrition")
