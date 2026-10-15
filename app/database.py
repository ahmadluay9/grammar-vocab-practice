"""SQLite persistence layer for daily 25-question sets and LLM grading results."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import DATA_DIR, DB_PATH


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path = DB_PATH) -> None:
    """Create database tables if they do not exist."""
    with get_connection(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS daily_sets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_str TEXT NOT NULL,
                unit_scope TEXT NOT NULL,
                model_name TEXT NOT NULL,
                total_questions INTEGER NOT NULL DEFAULT 25,
                contexts_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_daily_sets_date_unit
                ON daily_sets(date_str, unit_scope);

            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                set_id INTEGER NOT NULL,
                question_number INTEGER NOT NULL,
                context_id TEXT NOT NULL,
                unit_id TEXT NOT NULL,
                user_answer TEXT NOT NULL,
                score INTEGER NOT NULL,
                verdict TEXT NOT NULL,
                detailed_feedback TEXT NOT NULL,
                grammar_vocab_analysis TEXT NOT NULL,
                ideal_answer TEXT NOT NULL,
                example_usage TEXT NOT NULL,
                graded_by_model TEXT NOT NULL,
                graded_at TEXT NOT NULL,
                FOREIGN KEY(set_id) REFERENCES daily_sets(id),
                UNIQUE(set_id, question_number)
            );
            """
        )


def save_daily_set(
    date_str: str,
    unit_scope: str,
    model_name: str,
    contexts: list[dict[str, Any]],
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Persist a newly generated 25-question daily set."""
    init_db(db_path)
    total_q = sum(len(ctx.get("questions", [])) for ctx in contexts)
    now_iso = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO daily_sets (date_str, unit_scope, model_name, total_questions, contexts_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (date_str, str(unit_scope), model_name, total_q, json.dumps(contexts, ensure_ascii=False), now_iso),
        )
        set_id = cur.lastrowid
    return get_daily_set_by_id(set_id, db_path=db_path)  # type: ignore[return-value]


def _enrich_set_row(row: sqlite3.Row, conn: sqlite3.Connection) -> dict[str, Any]:
    set_id = row["id"]
    contexts: list[dict[str, Any]] = json.loads(row["contexts_json"])

    sub_rows = conn.execute(
        "SELECT * FROM submissions WHERE set_id = ? ORDER BY question_number ASC",
        (set_id,),
    ).fetchall()
    subs_by_qnum: dict[int, dict[str, Any]] = {
        r["question_number"]: {
            "question_number": r["question_number"],
            "user_answer": r["user_answer"],
            "score": r["score"],
            "verdict": r["verdict"],
            "detailed_feedback": r["detailed_feedback"],
            "grammar_vocab_analysis": r["grammar_vocab_analysis"],
            "ideal_answer": r["ideal_answer"],
            "example_usage": r["example_usage"],
            "graded_by_model": r["graded_by_model"],
            "graded_at": r["graded_at"],
        }
        for r in sub_rows
    }

    unit_breakdown: dict[str, dict[str, Any]] = {}
    category_breakdown: dict[str, dict[str, Any]] = {}
    all_scores: list[int] = []

    for ctx in contexts:
        ctx_scores: list[int] = []
        for q in ctx.get("questions", []):
            qnum = int(q["question_number"])
            sub = subs_by_qnum.get(qnum)
            q["submission"] = sub
            u_id = str(q.get("unit_id", ctx.get("unit_id", "1")))
            u_name = q.get("unit_name", ctx.get("unit_name", f"Unit {u_id}"))
            cat = q.get("category", "Grammar")

            if u_id not in unit_breakdown:
                unit_breakdown[u_id] = {
                    "unit_id": u_id,
                    "unit_name": u_name,
                    "total_questions": 0,
                    "answered_questions": 0,
                    "scores": [],
                }
            unit_breakdown[u_id]["total_questions"] += 1

            if cat not in category_breakdown:
                category_breakdown[cat] = {
                    "category": cat,
                    "total_questions": 0,
                    "answered_questions": 0,
                    "scores": [],
                }
            category_breakdown[cat]["total_questions"] += 1

            if sub is not None:
                score_val = int(sub["score"])
                ctx_scores.append(score_val)
                all_scores.append(score_val)
                unit_breakdown[u_id]["answered_questions"] += 1
                unit_breakdown[u_id]["scores"].append(score_val)
                category_breakdown[cat]["answered_questions"] += 1
                category_breakdown[cat]["scores"].append(score_val)

        ctx["answered_count"] = len(ctx_scores)
        ctx["average_score"] = round(sum(ctx_scores) / len(ctx_scores), 1) if ctx_scores else None

    unit_stats = []
    for u_info in unit_breakdown.values():
        scores = u_info.pop("scores")
        u_info["average_score"] = round(sum(scores) / len(scores), 1) if scores else None
        unit_stats.append(u_info)

    cat_stats = []
    for c_info in category_breakdown.values():
        scores = c_info.pop("scores")
        c_info["average_score"] = round(sum(scores) / len(scores), 1) if scores else None
        cat_stats.append(c_info)

    return {
        "set_id": set_id,
        "date_str": row["date_str"],
        "unit_scope": row["unit_scope"],
        "model_name": row["model_name"],
        "total_questions": row["total_questions"],
        "created_at": row["created_at"],
        "answered_count": len(all_scores),
        "average_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else None,
        "contexts": contexts,
        "unit_breakdown": unit_stats,
        "category_breakdown": cat_stats,
    }


def get_daily_set_by_id(set_id: int, db_path: Path = DB_PATH) -> dict[str, Any] | None:
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute("SELECT * FROM daily_sets WHERE id = ?", (set_id,)).fetchone()
        if not row:
            return None
        return _enrich_set_row(row, conn)


def get_latest_daily_set(date_str: str, unit_scope: str = "all", db_path: Path = DB_PATH) -> dict[str, Any] | None:
    """Return the latest 25-question set for a given date and unit scope."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM daily_sets
            WHERE date_str = ? AND unit_scope = ?
            ORDER BY id DESC LIMIT 1
            """,
            (date_str, str(unit_scope)),
        ).fetchone()
        if not row:
            return None
        return _enrich_set_row(row, conn)


def save_submissions(
    set_id: int,
    graded_items: list[dict[str, Any]],
    model_name: str,
    db_path: Path = DB_PATH,
) -> dict[str, Any]:
    """Upsert LLM-graded answers for a daily set and return the updated set."""
    init_db(db_path)
    now_iso = datetime.now().isoformat(timespec="seconds")
    with get_connection(db_path) as conn:
        for item in graded_items:
            score = max(1, min(100, int(item["score"])))
            conn.execute(
                """
                INSERT INTO submissions (
                    set_id, question_number, context_id, unit_id, user_answer,
                    score, verdict, detailed_feedback, grammar_vocab_analysis,
                    ideal_answer, example_usage, graded_by_model, graded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(set_id, question_number) DO UPDATE SET
                    user_answer = excluded.user_answer,
                    score = excluded.score,
                    verdict = excluded.verdict,
                    detailed_feedback = excluded.detailed_feedback,
                    grammar_vocab_analysis = excluded.grammar_vocab_analysis,
                    ideal_answer = excluded.ideal_answer,
                    example_usage = excluded.example_usage,
                    graded_by_model = excluded.graded_by_model,
                    graded_at = excluded.graded_at
                """,
                (
                    set_id,
                    int(item["question_number"]),
                    str(item.get("context_id", "")),
                    str(item.get("unit_id", "1")),
                    str(item["user_answer"]),
                    score,
                    str(item.get("verdict", "")),
                    str(item.get("detailed_feedback", "")),
                    str(item.get("grammar_vocab_analysis", "")),
                    str(item.get("ideal_answer", "")),
                    str(item.get("example_usage", "")),
                    model_name,
                    now_iso,
                ),
            )
    updated = get_daily_set_by_id(set_id, db_path=db_path)
    if not updated:
        raise ValueError(f"Daily set {set_id} not found after saving submissions.")
    return updated


def get_recent_context_titles(limit: int = 25, db_path: Path = DB_PATH) -> list[str]:
    """Return recently generated context titles & target words to prevent daily repetition."""
    init_db(db_path)
    titles: list[str] = []
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT contexts_json FROM daily_sets ORDER BY id DESC LIMIT 10"
        ).fetchall()
        for r in rows:
            try:
                contexts = json.loads(r["contexts_json"])
                for ctx in contexts:
                    title = ctx.get("title", "")
                    targets = [q.get("target_answer", "") for q in ctx.get("questions", [])]
                    if title:
                        titles.append(f"{title} (targets: {', '.join(targets)})")
                    if len(titles) >= limit:
                        return titles
            except Exception:
                continue
    return titles


def list_daily_history(limit: int = 30, db_path: Path = DB_PATH) -> list[dict[str, Any]]:
    """Return history of generated daily sets and their completion/average scores."""
    init_db(db_path)
    history: list[dict[str, Any]] = []
    with get_connection(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM daily_sets ORDER BY date_str DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        for row in rows:
            enriched = _enrich_set_row(row, conn)
            history.append(
                {
                    "set_id": enriched["set_id"],
                    "date_str": enriched["date_str"],
                    "unit_scope": enriched["unit_scope"],
                    "model_name": enriched["model_name"],
                    "total_questions": enriched["total_questions"],
                    "answered_count": enriched["answered_count"],
                    "average_score": enriched["average_score"],
                    "created_at": enriched["created_at"],
                    "unit_breakdown": enriched["unit_breakdown"],
                }
            )
    return history
