"""PostgreSQL 연결. 앱과 scripts/*.py가 모두 이 모듈을 통해 접속한다.

SQLite에서 옮겨온 이유: 배포 대상인 컨테이너 환경(App Runner/ECS)은 재배포 때
파일시스템이 초기화되어 db 파일이 통째로 사라진다. RDS 같은 관리형 DB가 필요하고,
로컬에서도 같은 엔진을 써야 방언 차이로 인한 사고를 막을 수 있다.

접속 정보는 DATABASE_URL 하나로만 받는다 (RDS도 같은 형식):
    postgresql://user:password@host:5432/dbname
"""
import os
import re
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

DEFAULT_DSN = "postgresql://dining:dining@localhost:5432/dining_maps"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "db" / "schema.sql"


def get_dsn() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DSN)


def get_connection(row_factory=dict_row):
    """psycopg 커넥션. 기본 row_factory가 dict_row라서 sqlite3.Row처럼
    컬럼명으로 접근할 수 있다 (row["name"])."""
    return psycopg.connect(get_dsn(), row_factory=row_factory)


def apply_schema(conn, path=SCHEMA_PATH):
    """Apply db/schema.sql one statement at a time.

    Every statement in schema.sql is CREATE ... IF NOT EXISTS / ADD COLUMN
    IF NOT EXISTS, so this is a no-op against an up-to-date DB -- safe to call
    before every write job as a guard against prod drifting from schema.sql
    (see the 'basis' column incident: compute_diet_score.py wrote it, prod
    didn't have it yet). Comments are stripped first because they contain
    their own ';' (e.g. "Append-only; never UPDATEd.") which would otherwise
    split a statement in half. One execute() per statement, not the whole
    file as one multi-statement blob -- that crashed Neon's pooled connection
    outright (psycopg.errors.ProtocolViolation: server conn crashed?) once
    schema.sql grew to include the CREATE MATERIALIZED VIEW blocks.
    """
    sql = re.sub(r"--.*", "", path.read_text(encoding="utf-8"))
    for statement in sql.split(";"):
        if statement.strip():
            conn.execute(statement)


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
