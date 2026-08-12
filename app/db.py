"""PostgreSQL 연결. 앱과 scripts/*.py가 모두 이 모듈을 통해 접속한다.

SQLite에서 옮겨온 이유: 배포 대상인 컨테이너 환경(App Runner/ECS)은 재배포 때
파일시스템이 초기화되어 db 파일이 통째로 사라진다. RDS 같은 관리형 DB가 필요하고,
로컬에서도 같은 엔진을 써야 방언 차이로 인한 사고를 막을 수 있다.

접속 정보는 DATABASE_URL 하나로만 받는다 (RDS도 같은 형식):
    postgresql://user:password@host:5432/dbname
"""
import os
from contextlib import contextmanager

import psycopg
from psycopg.rows import dict_row

DEFAULT_DSN = "postgresql://dining:dining@localhost:5432/dining_maps"


def get_dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DSN)


def get_connection(row_factory=dict_row):
    """psycopg 커넥션. 기본 row_factory가 dict_row라서 sqlite3.Row처럼
    컬럼명으로 접근할 수 있다 (row["name"])."""
    return psycopg.connect(get_dsn(), row_factory=row_factory)


@contextmanager
def connect():
    """with 블록을 벗어날 때 커밋(예외 시 롤백)하고 닫는다."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
