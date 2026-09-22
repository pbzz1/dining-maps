"""app 패키지를 import하는 순간 .env부터 읽는다.

app/main.py의 ALLOWED_ORIGINS처럼 모듈 최상단에서 환경변수를 읽는 코드가 있어서
로딩이 그보다 늦으면 값을 놓친다. 패키지 __init__은 app.* 중 무엇을 import하든
가장 먼저 실행되므로(scripts/*.py가 app.db 하나만 import하는 경우 포함)
여기가 유일하게 안전한 자리다.
"""
from app.env import load_dotenv_once

load_dotenv_once()
