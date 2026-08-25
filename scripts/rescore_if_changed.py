"""Re-run compute_diet_score.py only when its inputs changed.

"Inputs" = every menu_item (id/name/category -- category drives meal/drink
basis) + every nutrition_fact row + the scoring rules themselves (hash of
compute_diet_score.py). A fingerprint of all of that is kept in
diet_score_run; if it matches the last run, nothing happens.

Brand relative grades (20/30/30/20) are ranked live in app/main.py, so the
only thing that needs a scheduled refresh is the per-menu diet_score table
-- i.e. new brands getting scored at all, and menu-level percentiles.

Run by .github/workflows/rescore.yml daily; `--force` skips the check.
"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.db import connect  # noqa: E402
from scripts import compute_diet_score  # noqa: E402

SCORER = ROOT / "scripts" / "compute_diet_score.py"
SCHEMA_PATH = ROOT / "db" / "schema.sql"


def fingerprint(conn) -> str:
    data = conn.execute(
        """SELECT md5(
                 (SELECT coalesce(string_agg(id || ':' || name || ':' || coalesce(category, ''), ',' ORDER BY id), '')
                    FROM menu_item)
               || '|' ||
                 (SELECT coalesce(string_agg(menu_item_id || ':' || nutrient_name || ':' || value, ',' ORDER BY menu_item_id, nutrient_name), '')
                    FROM nutrition_fact)
           ) AS h"""
    ).fetchone()["h"]
    rules = hashlib.md5(SCORER.read_bytes()).hexdigest()
    return f"{data}-{rules}"


def main(force: bool = False) -> bool:
    """Returns True if scores were recomputed."""
    with connect() as conn:
        # This is the only writer that runs unattended (daily cron), so it's the
        # one place a schema.sql column added after the last manual load_data.py
        # run would otherwise silently drift from production -- see the 'basis'
        # column incident (compute_diet_score.py wrote it, prod didn't have it).
        # One statement per execute() -- sending the whole file as a single
        # multi-statement blob crashed the pooled Neon connection outright
        # (psycopg.errors.ProtocolViolation: server conn crashed?) once schema.sql
        # grew to include the CREATE MATERIALIZED VIEW blocks. Comments are
        # stripped first because they contain their own ';' (e.g. "Append-only;
        # never UPDATEd.") which would otherwise split a statement in half.
        sql = re.sub(r"--.*", "", SCHEMA_PATH.read_text(encoding="utf-8"))
        for statement in sql.split(";"):
            if statement.strip():
                conn.execute(statement)
        # compute_diet_score.main() opens its OWN connection (it's also run
        # standalone), so without an explicit commit here the schema changes
        # above are invisible to it -- a separate session can't see another
        # session's uncommitted DDL. This is what actually caused "column
        # basis does not exist" even though the ALTER ran moments earlier.
        conn.commit()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS diet_score_run (fingerprint TEXT NOT NULL, ran_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
        fp = fingerprint(conn)
        last = conn.execute("SELECT fingerprint FROM diet_score_run ORDER BY ran_at DESC LIMIT 1").fetchone()
        if not force and last and last["fingerprint"] == fp:
            print(f"unchanged ({fp[:12]}…); skipping")
            return False
        print(f"inputs changed -> rescoring ({fp[:12]}…)")
        compute_diet_score.main()
        conn.execute("INSERT INTO diet_score_run (fingerprint) VALUES (%s)", (fp,))
    return True


if __name__ == "__main__":
    main(force="--force" in sys.argv)
