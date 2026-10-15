"""LLM service powered by Google GenAI using the model configured in .env."""

from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import get_gcp_settings, get_model_name
from app.curriculum import (
    GENERAL_TOPICS,
    UnitData,
    build_general_unit_data,
    get_unit_by_id,
    load_units,
)


#Pydantic schemas for structured LLM output
class DialogueTurnSchema(BaseModel):
    speaker: str = Field(description="Speaker name, e.g., Frank, Carmen, John")
    role: str = Field(description="Speaker role or title, e.g., Hiring Manager, Candidate")
    text: str = Field(description="Dialogue line. If it contains a blank, use exact marker ___(N)___")


class BlankQuestionSchema(BaseModel):
    question_number: int = Field(description="Global question number as assigned")
    blank_marker: str = Field(description="Exact marker used in text, e.g. ___(1)___")
    lesson_name: str = Field(description="The lesson title this question tests")
    category: str = Field(description="One of: Grammar, Vocabulary, Expressions")
    answer_format: str = Field(
        default="word_or_phrase",
        description="Must be 'sentence' for conversation contexts (where the answer is a complete sentence) or 'word_or_phrase' for reading_passage contexts",
    )
    sentence_with_blank: str = Field(
        description="For conversations: the dialogue exchange/turn containing ___(N)___ (including the previous speaker's line if needed for context). For reading passages: the complete sentence containing ___(N)___."
    )
    clue: str = Field(
        description="For conversations: clear prompt instructing the learner to write a complete sentence with a specific communicative meaning AND specifying the target grammar structure, vocabulary word, or expression to include. For reading passages: clear cue explaining the required word/phrase meaning and part of speech."
    )
    hint: str = Field(
        description="Helpful hint such as a sentence starter + target keyword/grammar pattern (for conversations) or first letter/word count (for reading passages)"
    )
    target_answer: str = Field(
        description="For conversations: a COMPLETE, natural English sentence (ending with ., ?, or !) that fills the blank. For reading passages: the exact ideal word or phrase that fills the blank."
    )
    acceptable_answers: list[str] = Field(
        description="For conversations: 2-3 alternative complete sentences that also fit accurately. For reading passages: acceptable alternative words or phrases."
    )
    grammar_vocab_note: str = Field(
        description="Explanation of the grammar rule, vocabulary nuance, or expression from the lesson"
    )


class GeneratedContextSchema(BaseModel):
    title: str = Field(description="Engaging title for the conversation or reading passage")
    scenario_description: str = Field(
        description="1-2 sentence background setting the scene for the learner"
    )
    context_type: str = Field(description="Must be either 'conversation' or 'reading_passage'")
    lesson_name: str = Field(description="Primary lesson title covered by this context")
    turns: list[DialogueTurnSchema] = Field(
        default_factory=list,
        description="For 'conversation' type: 7 to 10 realistic multi-turn dialogue exchanges where 5 turns contain a full-sentence blank ___(N)___",
    )
    passage_paragraphs: list[str] = Field(
        default_factory=list,
        description="For 'reading_passage' type: 3 to 5 paragraphs (e.g. cover letter, email, article, report) containing the 5 blanks",
    )
    questions: list[BlankQuestionSchema] = Field(
        description="Exactly 5 related fill-in-the-blank questions embedded in this context"
    )


class GradedQuestionSchema(BaseModel):
    question_number: int = Field(description="The question number being graded")
    score: int = Field(
        description="Grade on a scale of 1 to 100 based on semantic accuracy, target unit mastery, grammar, sentence completeness (for conversations), word form, and spelling"
    )
    verdict: str = Field(
        description="Short verdict label: 'Excellent' (90-100), 'Good' (75-89), 'Partially Correct' (45-74), or 'Needs Improvement' (1-44)"
    )
    detailed_feedback: str = Field(
        description="Detailed, encouraging, and specific explanation of why the user's answer received this 1-100 score in the context of the passage or conversation"
    )
    grammar_vocab_analysis: str = Field(
        description="Specific breakdown of grammar, sentence structure, word form (noun/verb/adj/adv), collocation, or preposition usage"
    )
    ideal_answer: str = Field(description="The best answer(s) for this blank")
    example_usage: str = Field(
        description="A new example sentence demonstrating natural usage of the ideal answer"
    )


class GradingBatchResponseSchema(BaseModel):
    overall_feedback: str = Field(
        description="Concise summary feedback on the user's performance across these questions"
    )
    graded_questions: list[GradedQuestionSchema] = Field(
        description="Grading results for each submitted question"
    )


def create_genai_client() -> tuple[genai.Client, str]:
    """Instantiate the Google GenAI client and return (client, model_name) from .env."""
    settings = get_gcp_settings()
    model_name = get_model_name()

    if settings["use_vertex"] or settings["project"]:
        client = genai.Client(
            vertexai=True,
            project=str(settings["project"]) if settings["project"] else None,
            location=str(settings["location"] or "global"),
        )
    elif settings["api_key"]:
        client = genai.Client(api_key=str(settings["api_key"]))
    else:
        client = genai.Client()

    return client, model_name


def _normalize_blank_markers(
    raw_ctx: dict[str, Any],
    question_numbers: list[int],
) -> dict[str, Any]:
    """Ensure all 5 blanks use the canonical marker ___(N)___ and appear in the context body."""
    questions = raw_ctx.get("questions", [])
    # Enforce exact question numbers
    for idx, qnum in enumerate(question_numbers):
        if idx < len(questions):
            questions[idx]["question_number"] = qnum
            questions[idx]["blank_marker"] = f"___({qnum})___"

    def fix_text(text: str) -> str:
        for qnum in question_numbers:
            canonical = f"___({qnum})___"
            if canonical in text:
                continue
            # Replace common variants like [1], (1), ___1___, __(1)__, {1}, Blank 1
            patterns = [
                rf"_{{2,}}\s*\(?\s*{qnum}\s*\)?\s*_{{2,}}",
                rf"_{{2,}}\s*{qnum}\b",
                rf"\[\s*#?{qnum}\s*\]",
                r"\{\{\s*" + str(qnum) + r"\s*\}\}",
                rf"\(\s*{qnum}\s*\)\s*_{{2,}}",
                rf"_{{2,}}\s*\(\s*{qnum}\s*\)",
            ]
            for pat in patterns:
                if re.search(pat, text):
                    text = re.sub(pat, canonical, text, count=1)
                    break
        return text

    ctype = raw_ctx.get("context_type", "conversation")
    if ctype == "conversation":
        turns = raw_ctx.get("turns") or []
        for t in turns:
            t["text"] = fix_text(t.get("text", ""))
        combined = "\n".join(f"{t.get('speaker', 'Speaker')}: {t.get('text', '')}" for t in turns)
        # Ensure every question marker is present in at least one turn and marked as full-sentence answer
        for q in questions:
            qnum = q["question_number"]
            marker = f"___({qnum})___"
            q["answer_format"] = "sentence"
            target = (q.get("target_answer") or "").strip()
            if target and target[-1] not in ".?!":
                q["target_answer"] = f"{target}."
                target = q["target_answer"]
            q["sentence_with_blank"] = fix_text(q.get("sentence_with_blank", ""))
            if marker not in q["sentence_with_blank"]:
                if target and re.search(re.escape(target), q["sentence_with_blank"], re.IGNORECASE):
                    q["sentence_with_blank"] = re.sub(
                        re.escape(target), marker, q["sentence_with_blank"], count=1, flags=re.IGNORECASE
                    )
                else:
                    q["sentence_with_blank"] = f"{q['sentence_with_blank'].rstrip()} {marker}".strip()
            if marker not in combined:
                # Try replacing target_answer sentence in turns, or append a turn with sentence_with_blank
                replaced = False
                if target:
                    target_no_punct = target.rstrip(".?!")
                    for t in turns:
                        if re.search(re.escape(target), t["text"], re.IGNORECASE):
                            t["text"] = re.sub(
                                re.escape(target), marker, t["text"], count=1, flags=re.IGNORECASE
                            )
                            replaced = True
                            break
                        if target_no_punct and re.search(re.escape(target_no_punct), t["text"], re.IGNORECASE):
                            t["text"] = re.sub(
                                re.escape(target_no_punct) + r"[.?!]?",
                                marker,
                                t["text"],
                                count=1,
                                flags=re.IGNORECASE,
                            )
                            replaced = True
                            break
                if not replaced:
                    speaker = turns[-1]["speaker"] if turns else "Alex"
                    role = turns[-1].get("role", "Colleague") if turns else "Colleague"
                    turns.append({"speaker": speaker, "role": role, "text": q["sentence_with_blank"]})
                combined = "\n".join(f"{t.get('speaker', 'Speaker')}: {t.get('text', '')}" for t in turns)
        raw_ctx["turns"] = turns
        raw_ctx["content_text"] = combined
    else:
        paragraphs = raw_ctx.get("passage_paragraphs") or []
        paragraphs = [fix_text(p) for p in paragraphs]
        combined = "\n\n".join(paragraphs)
        for q in questions:
            qnum = q["question_number"]
            marker = f"___({qnum})___"
            q["answer_format"] = "word_or_phrase"
            q["sentence_with_blank"] = fix_text(q.get("sentence_with_blank", ""))
            if marker not in q["sentence_with_blank"]:
                target = q.get("target_answer", "")
                if target and re.search(re.escape(target), q["sentence_with_blank"], re.IGNORECASE):
                    q["sentence_with_blank"] = re.sub(
                        re.escape(target), marker, q["sentence_with_blank"], count=1, flags=re.IGNORECASE
                    )
                else:
                    q["sentence_with_blank"] = f"{q['sentence_with_blank'].rstrip('.')} {marker}."
            if marker not in combined:
                target = q.get("target_answer", "")
                replaced = False
                if target:
                    for i, p in enumerate(paragraphs):
                        if re.search(rf"\b{re.escape(target)}\b", p, re.IGNORECASE):
                            paragraphs[i] = re.sub(
                                rf"\b{re.escape(target)}\b", marker, p, count=1, flags=re.IGNORECASE
                            )
                            replaced = True
                            break
                if not replaced:
                    if paragraphs:
                        paragraphs[-1] = f"{paragraphs[-1].rstrip()} {q['sentence_with_blank']}"
                    else:
                        paragraphs.append(q["sentence_with_blank"])
                combined = "\n\n".join(paragraphs)
        raw_ctx["passage_paragraphs"] = paragraphs
        raw_ctx["content_text"] = combined

    return raw_ctx


def _generate_single_context(
    context_index: int,
    unit: UnitData,
    lesson_focus: str,
    context_type: str,
    question_numbers: list[int],
    date_str: str,
    recent_titles: list[str],
) -> dict[str, Any]:
    """Generate 1 context (multi-turn conversation or reading passage) with 5 fill-in-the-blank questions."""
    client, model_name = create_genai_client()
    q_start, q_end = question_numbers[0], question_numbers[-1]
    markers_list = ", ".join(f"___({n})___" for n in question_numbers)
    avoid_str = "\n".join(f"- {t}" for t in recent_titles[:10]) if recent_titles else "None"

    curriculum_md = unit.combined_curriculum_text()
    is_general = unit.level == "General" or str(unit.unit_id).startswith("general")
    context_desc = (
        "A realistic, engaging 8-10 turn dialogue (e.g., podcast discussion, interview, or thoughtful debate) between 2-3 named speakers"
        if (context_type == "conversation" and is_general)
        else "A realistic 8-10 turn professional dialogue between 2-3 named speakers"
        if context_type == "conversation"
        else "A cohesive, engaging 3-4 paragraph reading passage such as a magazine feature, analytical essay, science/culture article, or commentary"
        if is_general
        else "A cohesive 3-4 paragraph reading passage such as a cover letter, professional email, article, or workplace report"
    )

    if context_type == "conversation":
        format_specific_rules = f"""CONVERSATION FULL-SENTENCE BLANK REQUIREMENTS (CRITICAL):
- For this CONVERSATION context, every blank ({markers_list}) MUST require a **COMPLETE SENTENCE** as the answer (NOT a single word or short fragment).
- In `turns`, each blank marker {markers_list} replaces an ENTIRE sentence spoken by a character (either the speaker's whole dialogue line, e.g., `___(1)___`, or a complete sentence alongside another sentence in that speaker's turn, e.g., `"That makes sense. ___(1)___"`).
- `answer_format` MUST be `"sentence"` for all 5 questions.
- `target_answer` for each question MUST be a complete, natural English sentence (at least 6-16 words, starting with a capital letter and ending with `.`, `?`, or `!`) that fits seamlessly into that dialogue turn and uses a key grammar structure, vocabulary item, or expression from the curriculum/topic.
- `acceptable_answers` MUST contain 2-3 alternative complete sentences that also fit the dialogue turn and satisfy the grammar/vocabulary goal.
- `sentence_with_blank` MUST show the conversational exchange context for that blank (include the previous speaker's question/statement followed by the responding speaker's turn containing `___(N)___`, e.g., `"Interviewer: What led you to apply for this role? — Candidate: ___(1)___"`).
- `clue` MUST clearly tell the learner:
  (a) that they need to write a **complete sentence** and what communicative point/response to express in the dialogue, AND
  (b) the specific target grammar structure (e.g., present perfect, past simple, sequence connector, passive voice, conditional) or target vocabulary/expression from the lesson that they MUST include in their sentence, without giving away the entire sentence verbatim.
- `hint` MUST provide a helpful sentence starter or required keyword/pattern (e.g., `"Start with 'I have been...' and use the phrase 'in charge of'"`)."""
    else:
        format_specific_rules = f"""READING PASSAGE FILL-IN-THE-BLANK REQUIREMENTS:
- In `passage_paragraphs`, replace the target vocabulary words, collocations, or grammar phrases directly with {markers_list} in sequential order from {q_start} to {q_end}.
- `answer_format` MUST be `"word_or_phrase"` for all 5 questions.
- `target_answer` MUST be the exact ideal word or phrase that fills the blank.
- Because there are no multiple-choice options, each question's `clue` field MUST give the learner a clear, unambiguous guide on what word or phrase to fill in (for example: "Sequence adverb meaning 'afterward'", or "Noun form of 'accomplish'", or "Phrasal verb (2 words) meaning 'stop doing a habit'") WITHOUT revealing the exact answer string in the clue."""

    prompt = f"""You are an expert English curriculum designer creating daily practice material for {date_str}.
Target Unit / Topic: {unit.display_name} (Level: {unit.level})
Primary Lesson / Skill Focus: {lesson_focus}
Required Context Format: {context_type.upper()} ({context_desc})
Assigned Question Numbers: {q_start} through {q_end} (exact blank markers: {markers_list})

CURRICULUM / TOPIC REFERENCE MATERIAL:
{curriculum_md}

STRICT REQUIREMENTS:
1. Create ONE rich, natural {context_type} centered on "{lesson_focus}" within "{unit.display_name}".
2. Embed EXACTLY 5 fill-in-the-blank questions inside the {context_type} using the exact markers: {markers_list} in sequential order from {q_start} to {q_end}.
3. Every blank MUST test a key grammar structure, high-utility vocabulary word, collocation, phrasal verb, or idiomatic expression appropriate for improving the learner's vocabulary and grammar.
4. Format MUST be strictly FILL-IN-THE-BLANK. Do NOT include any multiple-choice options (no A/B/C/D choices).
5. {format_specific_rules}
6. Make sure the scenario is fresh and distinct from previous sessions:
{avoid_str}
"""

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeneratedContextSchema,
            temperature=0.7,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )

    parsed = json.loads(response.text)
    parsed["context_id"] = f"ctx_{context_index}"
    parsed["context_number"] = context_index
    parsed["unit_id"] = unit.unit_id
    parsed["unit_name"] = unit.display_name
    parsed["context_type"] = context_type

    normalized = _normalize_blank_markers(parsed, question_numbers)
    for q in normalized.get("questions", []):
        q["unit_id"] = unit.unit_id
        q["unit_name"] = unit.display_name
        q["context_id"] = normalized["context_id"]
        if not q.get("lesson_name"):
            q["lesson_name"] = lesson_focus

    return normalized


def build_context_plan(unit_scope: str, date_str: str) -> list[dict[str, Any]]:
    """Plan 5 contexts (5 questions each = 25 questions total) categorized by unit or general topic."""
    context_types = ["conversation", "reading_passage", "conversation", "reading_passage", "conversation"]

    # Case 1: Daily 25 General Topics Mix (5 diverse general topics x 5 questions = 25 questions)
    if unit_scope == "general":
        plan = []
        for i, topic in enumerate(GENERAL_TOPICS[:5]):
            topic_unit = build_general_unit_data(f"general:{topic['topic_id']}")
            q_nums = list(range(i * 5 + 1, (i + 1) * 5 + 1))
            plan.append(
                {
                    "context_index": i + 1,
                    "unit": topic_unit,
                    "lesson_focus": f"{topic['title']} — Vocabulary & Grammar Mastery",
                    "context_type": context_types[i],
                    "question_numbers": q_nums,
                }
            )
        return plan

    # Case 2: Specific General Topic (preset e.g. 'general:general_science' or custom e.g. 'general:Space Exploration')
    if unit_scope.startswith("general:") or any(t["topic_id"] == unit_scope for t in GENERAL_TOPICS):
        target_unit = build_general_unit_data(unit_scope)
        lessons = target_unit.lessons
        plan = []
        for i in range(5):
            lesson_focus = lessons[i].title if i < len(lessons) else target_unit.display_name
            q_nums = list(range(i * 5 + 1, (i + 1) * 5 + 1))
            plan.append(
                {
                    "context_index": i + 1,
                    "unit": target_unit,
                    "lesson_focus": lesson_focus,
                    "context_type": context_types[i],
                    "question_numbers": q_nums,
                }
            )
        return plan

    units = load_units()
    if not units:
        raise RuntimeError("No curriculum units found in Level/ directory.")

    if unit_scope != "all":
        target_unit = get_unit_by_id(unit_scope) or units[0]
        lessons = target_unit.lessons
        plan = []
        for i in range(5):
            if i < len(lessons):
                lesson_focus = f"Lesson {lessons[i].lesson_number} - {lessons[i].title}"
            else:
                all_titles = ", ".join(l.title for l in lessons)
                lesson_focus = f"Unit Synthesis ({all_titles})"
            q_nums = list(range(i * 5 + 1, (i + 1) * 5 + 1))
            plan.append(
                {
                    "context_index": i + 1,
                    "unit": target_unit,
                    "lesson_focus": lesson_focus,
                    "context_type": context_types[i],
                    "question_numbers": q_nums,
                }
            )
        return plan

    # For "all" scope: categorize across units (always featuring Unit 1 + rotating/covering other units)
    # Use a deterministic daily offset so different days emphasize different lesson combinations
    day_seed = sum(ord(c) for c in date_str)
    selected_units: list[UnitData] = []
    # Always include Unit 1 first (which has the primary markdown curriculum files)
    selected_units.append(units[0])
    other_units = units[1:] if len(units) > 1 else [units[0]]
    for i in range(4):
        u = other_units[(day_seed + i) % len(other_units)]
        selected_units.append(u)

    plan = []
    for i, u in enumerate(selected_units):
        lessons = u.lessons
        if lessons:
            chosen_lesson = lessons[(day_seed + i) % len(lessons)]
            lesson_focus = f"Lesson {chosen_lesson.lesson_number} - {chosen_lesson.title}"
        else:
            lesson_focus = u.display_name
        q_nums = list(range(i * 5 + 1, (i + 1) * 5 + 1))
        plan.append(
            {
                "context_index": i + 1,
                "unit": u,
                "lesson_focus": lesson_focus,
                "context_type": context_types[i],
                "question_numbers": q_nums,
            }
        )
    return plan


def generate_daily_25_questions(
    date_str: str,
    unit_scope: str = "all",
    recent_titles: list[str] | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Generate 25 fill-in-the-blank questions across 5 contexts (conversations & passages) using the .env model."""
    model_name = get_model_name()
    plan = build_context_plan(unit_scope=unit_scope, date_str=date_str)
    recent = recent_titles or []

    def run_item(item: dict[str, Any]) -> dict[str, Any]:
        return _generate_single_context(
            context_index=item["context_index"],
            unit=item["unit"],
            lesson_focus=item["lesson_focus"],
            context_type=item["context_type"],
            question_numbers=item["question_numbers"],
            date_str=date_str,
            recent_titles=recent,
        )

    with ThreadPoolExecutor(max_workers=5) as pool:
        contexts = list(pool.map(run_item, plan))

    contexts.sort(key=lambda c: c["context_number"])
    return contexts, model_name


def _grade_context_batch(
    context: dict[str, Any],
    items_to_grade: list[dict[str, Any]],
    model_name: str,
) -> dict[str, Any]:
    """Grade up to 5 fill-in-the-blank answers within a single conversation or reading passage context."""
    client, _ = create_genai_client()
    is_conversation = context.get("context_type") == "conversation"

    qa_Spec = []
    for item in items_to_grade:
        q = item["question"]
        user_ans = item["user_answer"]
        ans_fmt = q.get("answer_format") or ("sentence" if is_conversation else "word_or_phrase")
        qa_Spec.append(
            f"""Question #{q['question_number']} (Blank Marker: {q['blank_marker']}):
- Unit & Lesson: {q.get('unit_name', '')} / {q.get('lesson_name', '')}
- Category: {q.get('category', '')}
- Required Answer Format: {"COMPLETE SENTENCE (must be a full grammatical sentence fitting the conversation)" if ans_fmt == "sentence" else "WORD OR PHRASE"}
- Sentence / Exchange in context: {q.get('sentence_with_blank', '')}
- Clue shown to learner: {q.get('clue', '')}
- Reference Target Answer: {q.get('target_answer', '')}
- Sample Acceptable Alternatives: {', '.join(q.get('acceptable_answers', []))}
- Curriculum Rule: {q.get('grammar_vocab_note', '')}
- LEARNER'S SUBMITTED ANSWER: "{user_ans}"
"""
        )

    if is_conversation:
        rubric_text = """GRADING RUBRIC FOR CONVERSATION FULL-SENTENCE ANSWERS (Scale 1-100):
- IMPORTANT: For conversation blanks, the learner is required to write a COMPLETE SENTENCE that fits naturally into the dialogue and fulfills the communicative & grammar/vocabulary prompt in the clue. They do NOT need to match the Reference Target Answer word-for-word!
- 90-100 (Excellent): A complete, natural, grammatically accurate sentence that fits the dialogue exchange seamlessly and properly uses the target grammar structure, vocabulary word, or expression requested in the clue.
- 75-89 (Good): A complete sentence that fits the dialogue and incorporates the target concept, with only minor grammar, tense, preposition, punctuation, or phrasing slips.
- 45-74 (Partially Correct): Either (a) the learner wrote only an isolated word or short fragment instead of a full sentence (even if it uses the right keyword), OR (b) the learner wrote a full sentence that makes sense in the conversation but missed the specific grammar/vocabulary target required by the clue.
- 1-44 (Needs Improvement): Completely off-topic, grammatically incoherent, nonsensical, or left empty. (Minimum score is 1, maximum is 100)."""
    else:
        rubric_text = """GRADING RUBRIC FOR READING PASSAGE WORD/PHRASE BLANKS (Scale 1-100):
- 95-100: Exact target answer or an equally natural curriculum expression that fits the context, grammar, and tone flawlessly.
- 80-94: Correct meaning and grammar (such as a valid synonym) or the target expression with a minor spelling/capitalization/inflection slip.
- 60-79: Right core vocabulary root or grammar concept, but wrong word form (e.g., noun instead of adjective), wrong tense, or missing required preposition (e.g., 'graduated' instead of 'graduated from').
- 30-59: Partially related word or phrase that shows some understanding of the sentence but is grammatically or collocationally inaccurate.
- 1-29: Completely incorrect, nonsensical, or left blank/empty. (Minimum score is 1, maximum is 100)."""

    prompt = f"""You are an expert, supportive English language professor grading a learner's fill-in-the-blank responses.
Grade each submitted answer on a scale from 1 to 100 and provide detailed, actionable feedback.

CONTEXT ({context.get('context_type', 'passage').upper()} — {context.get('title', '')}):
Unit: {context.get('unit_name', '')} | Lesson: {context.get('lesson_name', '')}
{context.get('content_text', '')}

QUESTIONS AND LEARNER ANSWERS TO GRADE:
{chr(10).join(qa_Spec)}

{rubric_text}

Provide thorough `detailed_feedback` explaining why the learner's answer earned its 1-100 score, `grammar_vocab_analysis` explaining the grammar/vocabulary rule from the unit, `ideal_answer`, and `example_usage`.
"""

    response = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GradingBatchResponseSchema,
            temperature=0.2,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return json.loads(response.text)


def grade_user_answers(
    daily_set: dict[str, Any],
    answers_map: dict[int, str],
) -> dict[str, Any]:
    """Grade user answers on a 1-100 scale using the LLM configured in .env."""
    model_name = get_model_name()
    contexts = daily_set.get("contexts", [])

    batches: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    for ctx in contexts:
        items = []
        for q in ctx.get("questions", []):
            qnum = int(q["question_number"])
            if qnum in answers_map:
                items.append(
                    {
                        "question": q,
                        "user_answer": str(answers_map[qnum]).strip(),
                    }
                )
        if items:
            batches.append((ctx, items))

    if not batches:
        raise ValueError("No matching question numbers found to grade.")

    def run_batch(batch_tuple: tuple[dict[str, Any], list[dict[str, Any]]]) -> dict[str, Any]:
        ctx, items = batch_tuple
        res = _grade_context_batch(ctx, items, model_name=model_name)
        by_qnum = {int(g["question_number"]): g for g in res.get("graded_questions", [])}
        normalized_graded = []
        for it in items:
            q = it["question"]
            qnum = int(q["question_number"])
            g = by_qnum.get(qnum, {})
            score = max(1, min(100, int(g.get("score", 1))))
            normalized_graded.append(
                {
                    "question_number": qnum,
                    "context_id": ctx.get("context_id", ""),
                    "unit_id": q.get("unit_id", ctx.get("unit_id", "1")),
                    "user_answer": it["user_answer"],
                    "score": score,
                    "verdict": g.get("verdict")
                    or (
                        "Excellent"
                        if score >= 90
                        else "Good"
                        if score >= 75
                        else "Partially Correct"
                        if score >= 45
                        else "Needs Improvement"
                    ),
                    "detailed_feedback": g.get(
                        "detailed_feedback",
                        "Reviewed against the context and target unit curriculum.",
                    ),
                    "grammar_vocab_analysis": g.get(
                        "grammar_vocab_analysis",
                        q.get("grammar_vocab_note", ""),
                    ),
                    "ideal_answer": g.get("ideal_answer", q.get("target_answer", "")),
                    "example_usage": g.get("example_usage", ""),
                }
            )
        return {
            "context_id": ctx.get("context_id", ""),
            "overall_feedback": res.get("overall_feedback", ""),
            "graded_questions": normalized_graded,
        }

    with ThreadPoolExecutor(max_workers=min(5, len(batches))) as pool:
        batch_results = list(pool.map(run_batch, batches))

    all_graded: list[dict[str, Any]] = []
    feedbacks: list[str] = []
    for br in batch_results:
        all_graded.extend(br["graded_questions"])
        if br.get("overall_feedback"):
            feedbacks.append(br["overall_feedback"])

    all_graded.sort(key=lambda x: x["question_number"])
    avg_score = round(sum(x["score"] for x in all_graded) / len(all_graded), 1) if all_graded else 0.0

    return {
        "model_name": model_name,
        "graded_count": len(all_graded),
        "average_score": avg_score,
        "overall_feedback": " ".join(feedbacks),
        "graded_questions": all_graded,
    }
