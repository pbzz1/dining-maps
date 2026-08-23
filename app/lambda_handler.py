"""Lambda 진입점. Function URL 이벤트를 Mangum이 ASGI로 변환해 FastAPI에 넘긴다."""
from mangum import Mangum

from app.main import app

handler = Mangum(app)
