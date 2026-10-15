# FluentPulse AI — LLM-Powered English Learning App

An interactive English learning web application powered by Google Gemini (configured dynamically via `.env`).

## Key Features & Requirements Fulfilled

1. **25 New Questions Every Day, Categorized by Unit**:
   - Automatically generates **25 fill-in-the-blank questions** per daily set (5 contexts × 5 related questions = 25 questions), tracked by date (`YYYY-MM-DD`) and stored in SQLite (`data/learning_app.db`).
   - Categorizes questions across the curriculum units discovered from the `Level/` directory (`Unit 1: Job interviews`, `Unit 2: Technology`, `Unit 3: Traveling`, `Unit 4: Socializing in business`, `Unit 5: Law`, `Unit 6: What you read`), supporting both a cross-unit **Daily 25 Mix** and dedicated **Per-Unit 25-Question Sets**.
2. **Model Name Retrieved from `.env`**:
   - Reads `GEMINI_MODEL` (along with `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and `GOOGLE_GENAI_USE_ENTERPRISE`) directly from `.env` via `app/config.py`.
3. **Multi-Turn Conversations & Reading Passages**:
   - Presents questions inside rich **multi-turn dialogues** (8–10 speaker turns) and **reading passages** (cover letters, business emails, memos, and articles), with each context containing **5 related fill-in-the-blank questions**.
4. **Strictly Fill-in-the-Blank Format (No Multiple-Choice)**:
   - Every question is a fill-in-the-blank slot (`___(1)___` through `___(25)___`) rendered both inline inside the conversation/passage and in a synced question card with contextual clues and optional hints.
5. **LLM Grading on a 1–100 Scale with Detailed Feedback**:
   - Uses the `.env` LLM to evaluate answers in full context on a **1–100 scale** (`score: 1..100`) and provides:
     - Numeric score (`1–100`) and verdict (`Excellent`, `Good`, `Partially Correct`, `Needs Improvement`)
     - Detailed contextual feedback explaining why the answer earned its score
     - Grammar, vocabulary, word-form, and preposition breakdown
     - Ideal target answer(s) and example usage sentences
6. **25 General-Topic Questions for Vocabulary & Grammar Improvement**:
   - Generates **25 fill-in-the-blank questions** on **General Topics** (`unit_scope="general"` or `"general:<topic>"`) to help build B2–C2 vocabulary (collocations, phrasal verbs, idioms, word formation) and advanced grammar structures across 5 general domains (*Science, Nature & Environment*, *Psychology, Habits & Human Behavior*, *Culture, Arts & Everyday Idioms*, *Global Society, Economics & Work-Life*, and *History, Innovation & Human Stories*) or any custom topic entered in the UI/CLI.

## Quick Start

### Using `make` ([Makefile](Makefile))

```powershell
make install                          # Sync dependencies with uv
make run                              # Launch web app at http://127.0.0.1:8000
make dev                              # Launch web app with hot reload
make generate                         # Generate/inspect today's 25 questions (all units)
make generate-unit UNIT=1             # Generate/inspect 25 questions for Unit 1
make generate-general                 # Generate/inspect 25 questions for General Topics (Vocab & Grammar)
make generate-general TOPIC="Travel"  # Generate/inspect 25 questions for a custom General Topic
make test                             # Run end-to-end test suite
make clean                            # Clean __pycache__ directories
```

### Using `uv` directly

```powershell
# Launch the interactive web app at http://127.0.0.1:8000
uv run --active python main.py

# Generate / inspect today's 25 questions in the terminal (all units)
uv run --active python main.py --generate-only

# Generate 25 questions specifically for Unit 1 (Job interviews)
uv run --active python main.py --generate-only --unit 1

# Generate 25 General-Topic questions for vocabulary & grammar
uv run --active python main.py --generate-only --topic general
```

