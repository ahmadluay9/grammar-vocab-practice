"""End-to-end tests for FluentPulse AI English Learning Application."""

from __future__ import annotations

import os
from pathlib import Path
from fastapi.testclient import TestClient

from app.api import app
from app.config import ENV_PATH, get_model_name
from app.curriculum import load_units


client = TestClient(app)


def test_env_model_name_retrieval() -> None:
    """Requirement: Retrieve the model name from the .env file."""
    assert ENV_PATH.exists(), ".env file must exist"
    env_text = ENV_PATH.read_text(encoding="utf-8")
    assert "GEMINI_MODEL=" in env_text

    model_name = get_model_name()
    assert model_name == "gemini-3.8-flash"

    resp = client.get("/api/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["model_name"] == model_name
    assert data["daily_question_count"] == 25
    assert data["question_format"] == "fill-in-the-blank"
    assert data["grading_scale"] == "1-100"


def test_curriculum_units_loaded() -> None:
    """Requirement: Categorized by unit from Level/ directory."""
    units = load_units()
    assert len(units) >= 6
    unit_1 = units[0]
    assert unit_1.unit_number == 1
    assert "Job interviews" in unit_1.title
    assert unit_1.has_markdown_files is True
    assert len(unit_1.lessons) == 4

    resp = client.get("/api/units")
    assert resp.status_code == 200
    api_units = resp.json()["units"]
    assert len(api_units) >= 6


def test_daily_25_questions_structure_and_format() -> None:
    """Requirements:
    - Generate 25 new questions every day, categorized by unit
    - Present questions as multi-turn conversations or reading passages, with each context containing multiple related questions
    - Use a fill-in-the-blank format (no multiple-choice questions)
    """
    resp = client.get("/api/daily?unit_scope=all&auto_generate=true")
    assert resp.status_code == 200
    payload = resp.json()
    daily_set = payload["daily_set"]
    assert daily_set is not None
    assert daily_set["total_questions"] == 25
    assert daily_set["model_name"] == get_model_name()

    contexts = daily_set["contexts"]
    assert len(contexts) == 5

    context_types = {c["context_type"] for c in contexts}
    assert "conversation" in context_types
    assert "reading_passage" in context_types

    all_question_numbers = []
    for ctx in contexts:
        assert ctx.get("unit_id")
        assert ctx.get("unit_name")
        assert ctx.get("lesson_name")
        questions = ctx.get("questions", [])
        # Each context must contain multiple related questions (5 per context)
        assert len(questions) == 5
        content_text = ctx.get("content_text", "")
        for q in questions:
            qnum = q["question_number"]
            all_question_numbers.append(qnum)
            marker = f"___({qnum})___"
            assert q["blank_marker"] == marker
            assert marker in content_text, f"Blank marker {marker} must appear in context text"
            assert q.get("clue"), f"Question #{qnum} must have a fill-in-the-blank clue"
            assert q.get("target_answer"), f"Question #{qnum} must have a target_answer"
            if ctx["context_type"] == "conversation":
                assert q.get("answer_format") == "sentence", f"Conversation Q#{qnum} must have answer_format='sentence'"
                words = q["target_answer"].strip().split()
                assert len(words) >= 3, f"Conversation Q#{qnum} target_answer must be a sentence, got: {q['target_answer']}"
                assert q["target_answer"].strip()[-1] in ".?!", f"Conversation Q#{qnum} target_answer must end with sentence punctuation"
            else:
                assert q.get("answer_format") == "word_or_phrase"
            # Strictly NO multiple-choice options
            assert "options" not in q
            assert "choices" not in q

    assert sorted(all_question_numbers) == list(range(1, 26))


def test_llm_grading_scale_1_to_100_and_detailed_feedback() -> None:
    """Requirement: Use the LLM to grade user answers on a scale of 1-100 and provide detailed feedback."""
    daily_resp = client.get("/api/daily?unit_scope=all&auto_generate=true").json()
    daily_set = daily_resp["daily_set"]
    set_id = daily_set["set_id"]

    first_ctx = daily_set["contexts"][0]
    q1 = first_ctx["questions"][0]
    q2 = first_ctx["questions"][1]

    # Submit an exact target answer for Q1 and a partially flawed/wrong answer for Q2
    grade_resp = client.post(
        "/api/grade",
        json={
            "set_id": set_id,
            "answers": {
                str(q1["question_number"]): q1["target_answer"],
                str(q2["question_number"]): "wrongword",
            },
        },
    )
    assert grade_resp.status_code == 200
    result = grade_resp.json()["grading_result"]
    assert result["model_name"] == get_model_name()
    assert result["graded_count"] == 2

    graded_map = {g["question_number"]: g for g in result["graded_questions"]}
    g1 = graded_map[q1["question_number"]]
    g2 = graded_map[q2["question_number"]]

    assert 1 <= g1["score"] <= 100
    assert g1["score"] >= 85, f"Expected high score for exact target answer, got {g1['score']}"
    assert len(g1["detailed_feedback"]) > 20
    assert len(g1["grammar_vocab_analysis"]) > 10
    assert g1["ideal_answer"]

    assert 1 <= g2["score"] <= 100
    assert g2["score"] < 60, f"Expected low score for 'wrongword', got {g2['score']}"
    assert len(g2["detailed_feedback"]) > 20


def test_general_topics_25_questions_vocab_and_grammar() -> None:
    """Requirement: Generate 25 questions related to general topics to improve vocabulary and grammar."""
    units_resp = client.get("/api/units").json()
    assert "general_topics" in units_resp
    assert len(units_resp["general_topics"]) == 5

    # Verify study guide endpoint works for general topics
    guide_resp = client.get("/api/units/general")
    assert guide_resp.status_code == 200
    guide_data = guide_resp.json()
    assert guide_data["unit_id"] == "general"
    assert len(guide_data["lessons"]) == 5

    # Generate or load 25 general-topic questions
    resp = client.get("/api/daily?unit_scope=general&auto_generate=true")
    assert resp.status_code == 200
    daily_set = resp.json()["daily_set"]
    assert daily_set is not None
    assert daily_set["unit_scope"] == "general"
    assert daily_set["total_questions"] == 25
    assert len(daily_set["contexts"]) == 5

    all_qnums = []
    for ctx in daily_set["contexts"]:
        assert str(ctx["unit_id"]).startswith("general")
        assert ctx["unit_name"].startswith("General:")
        questions = ctx["questions"]
        assert len(questions) == 5
        for q in questions:
            all_qnums.append(q["question_number"])
            assert f"___({q['question_number']})___" in ctx["content_text"]
            assert q["category"] in ("Grammar", "Vocabulary", "Expressions")
            if ctx["context_type"] == "conversation":
                assert q.get("answer_format") == "sentence"
                assert len(q["target_answer"].strip().split()) >= 3
            assert "options" not in q
            assert "choices" not in q

    assert sorted(all_qnums) == list(range(1, 26))


if __name__ == "__main__":
    for fn in (
        test_env_model_name_retrieval,
        test_curriculum_units_loaded,
        test_daily_25_questions_structure_and_format,
        test_general_topics_25_questions_vocab_and_grammar,
        test_llm_grading_scale_1_to_100_and_detailed_feedback,
    ):
        fn()
        print(f"PASS: {fn.__name__}")
    print("ALL TESTS PASSED!")


