"""FastAPI backend for the LLM-powered English learning application."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import STATIC_DIR, get_gcp_settings, get_model_name
from app.curriculum import get_general_topics, get_unit_by_id, load_units
from app.database import (
    get_daily_set_by_id,
    get_latest_daily_set,
    get_recent_context_titles,
    init_db,
    list_daily_history,
    save_daily_set,
    save_submissions,
)
from app.llm_service import generate_daily_25_questions, grade_user_answers

app = FastAPI(
    title="FluentPulse AI — LLM English Learning App",
    description="Daily 25 fill-in-the-blank questions in multi-turn conversations and reading passages, categorized by unit or general topic and graded 1-100 by Gemini.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateDailyRequest(BaseModel):
    date_str: str | None = Field(default=None, description="Target date YYYY-MM-DD (defaults to today)")
    unit_scope: str = Field(
        default="all",
        description="Scope: 'all' (cross-unit), '1'..'6' (specific unit), 'general' (25 general vocab & grammar questions), or 'general:<topic>'",
    )


class AnswerItem(BaseModel):
    question_number: int
    user_answer: str


class GradeAnswersRequest(BaseModel):
    set_id: int
    answers: dict[str, str] | list[AnswerItem]


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/api/config")
def api_get_config() -> dict[str, Any]:
    """Return active .env configuration including the LLM model name."""
    settings = get_gcp_settings()
    units = load_units()
    general_topics = get_general_topics()
    return {
        "model_name": get_model_name(),
        "project": settings["project"],
        "location": settings["location"],
        "use_vertex": settings["use_vertex"],
        "env_file": settings["env_file"],
        "today": date.today().isoformat(),
        "daily_question_count": 25,
        "question_format": "fill-in-the-blank",
        "grading_scale": "1-100",
        "total_units": len(units),
        "general_topics_count": len(general_topics),
    }


@app.get("/api/units")
def api_list_units() -> dict[str, Any]:
    """Return all curriculum units and general topics."""
    units = load_units()
    general_topics = get_general_topics()
    return {
        "units": [u.to_dict(include_content=False) for u in units],
        "total_units": len(units),
        "general_topics": general_topics,
    }


@app.get("/api/units/{unit_id:path}")
def api_get_unit_detail(unit_id: str) -> dict[str, Any]:
    """Return full curriculum study guide for a specific unit or general topic."""
    unit = get_unit_by_id(unit_id)
    if not unit:
        raise HTTPException(status_code=404, detail=f"Unit '{unit_id}' not found.")
    return unit.to_dict(include_content=True)


@app.get("/api/daily")
def api_get_daily_set(
    date_str: str | None = Query(default=None, description="Date in YYYY-MM-DD format"),
    unit_scope: str = Query(
        default="all",
        description="Unit scope: 'all', unit_id ('1'..'6'), 'general', or 'general:<topic>'",
    ),
    auto_generate: bool = Query(default=True, description="Automatically generate if missing for this date"),
) -> dict[str, Any]:
    """Retrieve the 25-question daily set for the specified date and unit scope."""
    target_date = date_str or date.today().isoformat()
    existing = get_latest_daily_set(date_str=target_date, unit_scope=unit_scope)
    if existing:
        return {"status": "ready", "daily_set": existing, "generated_now": False}

    if not auto_generate:
        return {"status": "empty", "daily_set": None, "generated_now": False}

    recent_titles = get_recent_context_titles(limit=20)
    contexts, model_name = generate_daily_25_questions(
        date_str=target_date,
        unit_scope=unit_scope,
        recent_titles=recent_titles,
    )
    saved = save_daily_set(
        date_str=target_date,
        unit_scope=unit_scope,
        model_name=model_name,
        contexts=contexts,
    )
    return {"status": "ready", "daily_set": saved, "generated_now": True}


@app.post("/api/daily/generate")
def api_generate_new_daily_set(req: GenerateDailyRequest) -> dict[str, Any]:
    """Force generation of a new 25-question set for the given date and unit scope."""
    target_date = req.date_str or date.today().isoformat()
    recent_titles = get_recent_context_titles(limit=25)
    contexts, model_name = generate_daily_25_questions(
        date_str=target_date,
        unit_scope=req.unit_scope,
        recent_titles=recent_titles,
    )
    saved = save_daily_set(
        date_str=target_date,
        unit_scope=req.unit_scope,
        model_name=model_name,
        contexts=contexts,
    )
    return {"status": "ready", "daily_set": saved, "generated_now": True}


@app.get("/api/daily/{set_id}")
def api_get_set_by_id(set_id: int) -> dict[str, Any]:
    """Retrieve a specific daily set by its database ID."""
    daily_set = get_daily_set_by_id(set_id)
    if not daily_set:
        raise HTTPException(status_code=404, detail=f"Daily set {set_id} not found.")
    return {"status": "ready", "daily_set": daily_set}


@app.post("/api/grade")
def api_grade_submissions(req: GradeAnswersRequest) -> dict[str, Any]:
    """Grade one or more fill-in-the-blank answers on a 1-100 scale using the LLM."""
    daily_set = get_daily_set_by_id(req.set_id)
    if not daily_set:
        raise HTTPException(status_code=404, detail=f"Daily set {req.set_id} not found.")

    answers_map: dict[int, str] = {}
    if isinstance(req.answers, dict):
        for k, v in req.answers.items():
            answers_map[int(k)] = str(v)
    else:
        for item in req.answers:
            answers_map[int(item.question_number)] = str(item.user_answer)

    if not answers_map:
        raise HTTPException(status_code=400, detail="No answers provided for grading.")

    grading_result = grade_user_answers(daily_set=daily_set, answers_map=answers_map)
    updated_set = save_submissions(
        set_id=req.set_id,
        graded_items=grading_result["graded_questions"],
        model_name=grading_result["model_name"],
    )
    return {
        "status": "graded",
        "grading_result": grading_result,
        "daily_set": updated_set,
    }


@app.get("/api/history")
def api_get_history(limit: int = Query(default=30, ge=1, le=100)) -> dict[str, Any]:
    """Return history of daily 25-question sets and unit mastery scores."""
    return {"history": list_daily_history(limit=limit)}


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    index_file = STATIC_DIR / "index.html"
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="Frontend index.html not found.")
    return FileResponse(str(index_file))
