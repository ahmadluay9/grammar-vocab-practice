"""Entrypoint for FluentPulse AI — LLM-Powered English Learning Application."""

from __future__ import annotations

import argparse
from datetime import date

import uvicorn

from app.config import get_gcp_settings, get_model_name
from app.curriculum import load_units
from app.database import (
    get_latest_daily_set,
    get_recent_context_titles,
    init_db,
    save_daily_set,
    save_submissions,
)
from app.llm_service import generate_daily_25_questions, grade_user_answers


def ensure_daily_set(target_date: str, unit_scope: str = "all", force_new: bool = False) -> dict:
    """Ensure a 25-question daily set exists for the given date and unit scope."""
    init_db()
    if not force_new:
        existing = get_latest_daily_set(date_str=target_date, unit_scope=unit_scope)
        if existing:
            return existing

    model_name = get_model_name()
    print(f"[FluentPulse AI] Generating 25 fill-in-the-blank questions for {target_date} (scope={unit_scope}) using model '{model_name}' from .env...")
    recent_titles = get_recent_context_titles(limit=20)
    contexts, used_model = generate_daily_25_questions(
        date_str=target_date,
        unit_scope=unit_scope,
        recent_titles=recent_titles,
    )
    saved = save_daily_set(
        date_str=target_date,
        unit_scope=unit_scope,
        model_name=used_model,
        contexts=contexts,
    )
    print(f"[FluentPulse AI] Successfully generated daily set #{saved['set_id']} with {saved['total_questions']} questions across {len(saved['contexts'])} contexts.")
    return saved


def run_cli_demo(target_date: str, unit_scope: str, force_new: bool = False) -> None:
    """Run an interactive CLI session or print summary of the 25 daily questions."""
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    daily_set = ensure_daily_set(target_date=target_date, unit_scope=unit_scope, force_new=force_new)
    print("=" * 76)
    print(f"FluentPulse AI | Date: {daily_set['date_str']} | Model (.env): {daily_set['model_name']}")
    print(f"Total Questions: {daily_set['total_questions']} | Scope: {daily_set['unit_scope']}")
    print("=" * 76)
    for ctx in daily_set["contexts"]:
        is_conv = ctx["context_type"] == "conversation"
        fmt_tag = "FULL-SENTENCE ANSWERS" if is_conv else "WORD/PHRASE ANSWERS"
        print(f"\n[{ctx['context_type'].upper()} — {fmt_tag}] {ctx['unit_name']} - {ctx['lesson_name']}")
        print(f"Title: {ctx['title']}")
        print("-" * 76)
        print(ctx["content_text"])
        print("-" * 76)
        for q in ctx["questions"]:
            q_fmt = "Sentence" if (is_conv or q.get("answer_format") == "sentence") else "Word/Phrase"
            print(f"  Q#{q['question_number']} [{q_fmt} | {q['category']}]: {q['clue']}")
    print("\nRun `uv run python main.py` to launch the interactive web application at http://127.0.0.1:8000")


def main() -> None:
    parser = argparse.ArgumentParser(description="FluentPulse AI — LLM English Learning App")
    parser.add_argument("--host", default="127.0.0.1", help="Web server host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Web server port (default: 8000)")
    parser.add_argument("--date", default=date.today().isoformat(), help="Target date YYYY-MM-DD")
    parser.add_argument(
        "--unit",
        default="all",
        help="Unit scope ('all', unit number '1'..'6', 'general', or 'general:<topic>')",
    )
    parser.add_argument(
        "--topic",
        default=None,
        help="Optional general topic name (e.g. 'Science', 'Travel', or 'general') to generate 25 vocabulary & grammar questions",
    )
    parser.add_argument("--generate-only", action="store_true", help="Generate/display today's 25 questions and exit")
    parser.add_argument("--force-new", action="store_true", help="Force generating a new 25-question set")
    args = parser.parse_args()

    target_scope = args.unit
    if args.topic:
        target_scope = "general" if args.topic.strip().lower() == "general" else f"general:{args.topic.strip()}"

    settings = get_gcp_settings()
    units = load_units()
    print(f"Loaded .env configuration -> GEMINI_MODEL={settings['model_name']} | Units discovered: {len(units)}")

    if args.generate_only:
        run_cli_demo(target_date=args.date, unit_scope=target_scope, force_new=args.force_new)
        return

    uvicorn.run("app.api:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()

