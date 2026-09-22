"""로컬 개발용 .env 로더.

프론트(frontend-react/.env)와 달리 백엔드는 환경변수만 읽었다. 그래서 DATABASE_URL을
터미널마다 다시 넣어야 했고, Windows cmd에서는 Neon 문자열의 '&' 때문에
`set "DATABASE_URL=...&channel_binding=require"` 처럼 따옴표까지 신경 써야 했다.
저장소 루트의 .env를 읽어서 그 수고를 없앤다.

이미 들어있는 환경변수는 덮어쓰지 않는다(override=False). 배포(Lambda/App Runner)와
Actions는 진짜 환경변수로 값을 주입하는데, 어쩌다 .env가 이미지에 섞여 들어가도
그쪽이 이겨야 한다 -- 로컬 파일이 운영 설정을 조용히 갈아끼우는 사고를 막는다.

python-dotenv가 없는 환경에서는 조용히 넘어간다. docker/Dockerfile.airflow는
requirements-airflow.txt만 깔기 때문에 이 패키지가 없는데, 거기서는 Airflow가
환경변수를 직접 주므로 .env가 필요 없다.
"""
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def load_dotenv_once() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(ENV_PATH, override=False)
