# Exam Grading Agent

## Purpose

This repository contains a Python agent that coordinates several MCP tools to retrieve an exam, analyze spelling and grammar, grade answers, and calculate a final grade.

The intended workflow is:

1. Identify the subject.
2. Retrieve the exam questions and the student's answers.
3. Analyze spelling and grammar.
4. Grade the answers using a language model and retrieved teaching material.
5. Calculate the final grade using the subject rubric.

## Structure

- `Agent.py`: console application and LangGraph workflow.
- `config/settings.py`: typed application settings loaded from environment variables.
- `observability/metrics_logger.py`: SQLite persistence for tool and workflow metrics.
- `tools/Common.py`: Pydantic models, subjects, themes, indirect rubric data, and dataset paths.
- `tools/SubjectRetriever.py`: identifies a subject from text.
- `tools/ExamRetriever.py`: reads questions and answers from the dataset files.
- `tools/SpellingChecker.py`: uses LanguageTool to detect Spanish errors.
- `tools/ExamGrader.py`: prepares PDF retrieval and grades answers with Cohere or Ollama.
- `tools/FinalGradeCalculator.py`: applies weights and spelling penalties.
- `tools/Wikipedia.py`: independent auxiliary tool; it is not part of the workflow configured in `Agent.py`.
- `tools/SpellingCheckerOLD.py`: old implementation, not used by the agent.

## Requirements

Python 3.11 or later is required, together with the local dataset referenced by `tools/Common.py`:

- `../DataSet/ResultadosPLENTAS_anonimizado_consentimiento`
- `../DataSet/TemasInteligenciaArtificial/pdfs`
- `../DataSet/TemasBasesdeDatosBigData`

Suggested installation:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -U mcp langchain langchain-core langchain-community langgraph langchain-openai langchain-cohere cohere langchain-mcp-adapters langgraph-checkpoint-sqlite aiosqlite pypdf sentence-transformers chromadb faiss-cpu pandas language-tool-python wikipedia
```

The exact dependency list should be pinned in a `requirements.txt` or `pyproject.toml` file to make experiments reproducible.

Application settings are defined in `config/settings.py` as the typed `AppSettings` dataclass. Values are loaded from environment variables when the application starts:

| Environment variable | Type | Default | Purpose |
| --- | --- | --- | --- |
| `COHERE_API_KEY` | string | required | Cohere API key |
| `LANGGRAPH_DEBUG` | boolean | `false` | Enables LangGraph debug output |
| `EXAM_GRADER_MODE` | `test` or `llm` | `llm` | Selects synthetic or LLM-based grading |
| `AGENT_CHECKPOINT_DB` | string | `agentCheckpoints.sqlite` | Checkpoint database path |
| `AGENT_METRICS_DB` | string | `metrics.sqlite` | Metrics database path |

## Configuration

The Cohere key must not be written in the source code. Define it in the PowerShell session:

```powershell
$env:COHERE_API_KEY = "<new-key>"
python Agent.py
```

LangGraph debug output is disabled by default. Enable it for a run with:

```powershell
$env:LANGGRAPH_DEBUG = "true"
python Agent.py
```

Accepted true values are `1`, `true`, `yes`, and `on`. Any other value disables debug output.

The key that was previously exposed in the source code must be revoked and regenerated with the provider. It must not be stored in the repository or in metrics.

The process must be started from the repository root because the MCP servers receive paths such as `tools\ExamRetriever.py`.

For local development, you can copy the key into the ignored `runAgentLocal.py` launcher and run:

```powershell
python runAgentLocal.py
```

## Running the Agent

```powershell
python Agent.py
```

Alternatively, run `python runAgentLocal.py` after configuring the local key as described above.

At startup, the agent asks how many consecutive exams to grade, starting with DNI 1. For example, entering `3` sends a separate grading request for DNI 1, then 2, then 3. Enter `0` to skip the batch; after the batch, the usual interactive prompt remains available.

Example request:

```text
Grade the exam for the Artificial Intelligence subject belonging to student with ID 1 and name Jacobo Farray.
```

To exit, enter `exit`, `quit`, or `q`.

Checkpoints are stored in `agentCheckpoints.sqlite` and metrics in `metrics.sqlite`. These are local runtime data and are excluded from Git.

## Main Contracts

### Exam Retrieval

`ExamRetriever` receives an `ExamRequestModel`:

- `subjectId`: `1` for Big Data Databases or `2` for Artificial Intelligence.
- `studentId`: student identifier.
- `studentName`: optional and currently not used for lookup.

It returns an `ExamToGradeModel` containing one question per configured theme and the available answers.

### Language Analysis

`SpellingChecker` receives the complete exam and returns, for each question, the number of errors, detected words, suggestions, and corrected text. Empty answers are accepted and skipped.

### Conceptual Grading

`ExamGrader` is prepared to use PDF material for each theme. In the current experimental state, `gradeExam_async` deliberately calls `gradeExamTest`, which generates deterministic test grades. Therefore, the current execution does not represent LLM-based grading.

The mode is controlled with `EXAM_GRADER_MODE`. It defaults to `llm`. Use `test` for deterministic local testing without calling the grading model:

```powershell
$env:EXAM_GRADER_MODE = "test"
python runAgentLocal.py
```

For LLM grading:

```powershell
$env:EXAM_GRADER_MODE = "llm"
python runAgentLocal.py
```

To enable real grading:

1. Ensure the configured PDF material exists.
2. Explicitly select Cohere or Ollama in the grader.
3. Validate model output with a structured parser and evaluation tests.

This change may take time because it loads PDFs, embeddings, and models.

### Final Grade

The current rubric is:

- Artificial Intelligence: `Tema2` 20%, `Tema4` 30%, `Tema6` 20%, `Tema8` 30%.
- Big Data Databases: `Tema5`, `Tema6`, `Tema7`, `Tema9`, and `Tema10`, 20% each.
- Spelling penalty: `0.5` points per error.

The final grade is constrained to `[0, 10]` and rounded to two decimal places. If a conceptual grade is missing for a rubric theme, an explicit error is raised. Missing spelling results do not apply a penalty.

## Changes Applied in This Review

- Removed the embedded Cohere key from `Agent.py` and `ExamGrader.py`.
- Added the fields that the grader actually constructs to the grading model.
- Added `corrected_text` to spelling-analysis results.
- Corrected the Big Data Databases rubric so it matches its configured themes.
- Made the spelling penalty configurable and consistent.
- Added handling for empty answers and incomplete data in final-grade calculation.
- Fixed Windows path escape warnings.
- Added `.gitignore` entries for SQLite databases, checkpoints, and bytecode.

## Risks and Prioritized Improvements

### High Priority

1. **Rotate the exposed key.** The environment variable prevents new exposure but does not invalidate the old key.
2. **Remove sensitive data from metrics.** `tools_trace` and `MetricsLogger` may store arguments and student answers. Apply data minimization, anonymization, and a retention policy.
3. **Separate test and production modes.** The synthetic grader should be enabled through explicit configuration and must not remain connected to the MCP tool by default.
4. **Add authentication and input validation** if the agent is exposed beyond a local console.

### Medium Priority

1. Reuse a stable `thread_id` per student, subject, and exam session; `SessionManager.get_thread()` currently creates a new one for every request.
2. Convert the blocking `llm.invoke` calls in `chat_node` and `planner_node` to asynchronous equivalents, or run them outside the event loop.
3. Move paths, model names, weights, and limits into validated configuration, preferably using `pathlib`.
4. Replace text-based grade extraction with structured output validated in the `0` to `10` range.
5. Use `questionId` in addition to `theme` when matching results; a theme should not be the only key if it can be repeated.
6. Add retry backoff, record the final error, and avoid retrying validation errors indiscriminately.
7. Close and correctly reuse MCP clients and LanguageTool resources throughout the process lifetime.

### Maintainability

1. Create a `pyproject.toml` or `requirements.txt` with pinned versions and separate Cohere, Ollama, and development dependencies.
2. Add `pytest` unit tests for retrieval, empty-answer handling, rubrics, and grade calculation.
3. Add reproducible grader evaluation: an annotated answer set, agreement with teachers, MAE, and edge cases.
4. Remove `SpellingCheckerOLD.py`, unused imports, and debugging code when no longer needed.
5. Use standard level-based logging instead of `print`, and do not log complete answers by default.

## Quick Checks

Compile all modules:

```powershell
python -m compileall -q .
```

Run static checks from VS Code/Pylance and execute tests once they are added. Compilation only detects syntax errors; it does not prove that the PDFs exist, the key is valid, LanguageTool is available, or that LLM grading is pedagogically reliable.

## Recommended Next Iteration

Before connecting the agent to real users, complete these steps in order: rotate credentials, enable real grading through explicit configuration, add tests for grade calculation and Pydantic contracts, anonymize metrics, implement persistent sessions, and evaluate results against teacher grades.
