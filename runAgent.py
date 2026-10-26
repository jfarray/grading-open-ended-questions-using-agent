"""Versioned launcher template for Agent.py.

Set COHERE_API_KEY in the environment before running this file.
Set LANGGRAPH_DEBUG=true to enable LangGraph debug output.
Set EXAM_GRADER_MODE=test or llm to select the grading mode.
"""

import asyncio
import os


if not os.environ.get("COHERE_API_KEY"):
    raise RuntimeError(
        "Set the COHERE_API_KEY environment variable before running runAgent.py."
    )

# Use LLM grading unless the caller explicitly selects another mode.
os.environ.setdefault("EXAM_GRADER_MODE", "llm")

from Agent import main

# Example usage:
"""
Corrige el examen de la asignatura Inteligencia Artificial del estudiante con Dni 1 y nombre Jacobo Farray.

Corrige ortográficamente el examen de la asignatura Inteligencia Artificial del estudiante con Dni 1 y nombre Jacobo Farray.

"""

if __name__ == "__main__":
    asyncio.run(main())