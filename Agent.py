"""
Requirements:
pip install -U mcp langchain langchain_core langchain_community langgraph langchain-openai langchain-cohere cohere langchain-mcp-adapters langgraph.checkpoint.sqlite aiosqlite pypdf sentence-transformers chromadb faiss-cpu

"""

import asyncio
import os
from pathlib import Path
from typing import List, Tuple
import json
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from langchain_cohere import ChatCohere
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_mcp_adapters.tools import load_mcp_tools, BaseTool
from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import tools_condition, ToolNode
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph.message import AnyMessage, add_messages
from typing_extensions import TypedDict
from typing import Annotated
from langchain_mcp_adapters.client import MultiServerMCPClient
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
import time
import sqlite3

from observability.metrics_logger import MetricsLogger
from config.settings import settings

metrics = MetricsLogger(settings.metrics_db_path)


# ------------------------------
# Define MCP servers
# ------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent

mcpServers: List[Tuple[str, Path]] = [
    ("SubjectRetriever", PROJECT_ROOT / "tools" / "SubjectRetriever.py"),
    ("ExamRetriever", PROJECT_ROOT / "tools" / "ExamRetriever.py"),
    ("SpellingGrammarChecker", PROJECT_ROOT / "tools" / "SpellingChecker.py"),
    ("ExamGrader", PROJECT_ROOT / "tools" / "ExamGrader.py"),
    ("FinalGradeCalculator", PROJECT_ROOT / "tools" / "FinalGradeCalculator.py"),
]


# ------------------------------
# Define LangGraph state
# ------------------------------

class State(TypedDict):
    messages: Annotated[List[AnyMessage], add_messages]
    
    
    
    last_tools_used: List[str]
    last_tool_signature: str | None
    last_tool_results: List[str]

    tools_trace: List[dict]
    failed_tools: List[str]
    tool_retries: dict

    step_count: int
    stuck_counter: int


    # useful for replan policy
    route: str   # "chat" | "replan" | "end"

class SessionManager:
    def __init__(self):
        self.sessions = {}

    def get_thread(self):
        # Generate a unique thread ID for each session
        # TODO: implement logic to retrieve existing thread based on user input (e.g., DNI, subject_id) instead of always creating a new one
        key = uuid.uuid4().hex  

        if key not in self.sessions:
            self.sessions[key] = {
                "thread_id": f"thread_{key}",
                "state": {}
            }

        return self.sessions[key]["thread_id"]

# ------------------------------
# Load MCP tools and keep sessions alive
# ------------------------------

async def loadAllMcpServerTools():
    params = {}
    # Propagate the current environment, including API keys, to MCP subprocesses.
    mcp_environment = os.environ.copy()
    existing_pythonpath = mcp_environment.get("PYTHONPATH")
    python_paths = [str(PROJECT_ROOT)]
    if existing_pythonpath:
        python_paths.append(existing_pythonpath)
    mcp_environment["PYTHONPATH"] = os.pathsep.join(python_paths)

    for name, path in mcpServers:
        params[name] = {
            "command": "python",
            "args": [str(path)],
            "transport": "stdio",
            "env": mcp_environment,
        }
    client = MultiServerMCPClient(params)

    try:
        return await client.get_tools()
    except Exception as error:
        raise RuntimeError(
            "No se pudieron cargar las tools MCP. Revisa la salida del servidor "
            "indicado en la excepción original."
        ) from error


# ------------------------------
# Build LangGraph agent
# ------------------------------

async def create_graph(tools: List[BaseTool], checkpointer: AsyncSqliteSaver) -> StateGraph:
    llm = ChatCohere(
        model="command-a-03-2025",   #"command-a-03-2025",
        temperature=0,
        cohere_api_key=settings.cohere_api_key
    )

    llm_with_tools = llm.bind_tools(tools)

    # System prompt + user/assistant messages
    prompt_template = ChatPromptTemplate.from_messages([
        ("system",
         "Eres un asistente que utiliza herramientas para corregir exámenes en idioma español. "
         "Puedes corregir un examen al completo utilizando todas las herramientas disponibles ó puedes corregir solamente una parte del examen utilizando solo la herramienta necesaria (por ejemplo, solo la herramienta de corrección ortográfica)."
         "Siempre necesitarás obtener la asignatura y el examen del estudiante para poder corregir cualquier parte del examen, incluso si solo se corrige la ortografía. "
         "Para corregir un examen al completo, debes seguir estos pasos: "
         "1. Obtén el Id de la asignatura que hay que corregir, "
         "2. Luego obtén el examen del estudiante para la asignatura especificada. Para ello utiliza el Dni del estudiante y el id de la asignatura, "
         "3. Utilizando el examen completo obtenido en el paso 2, verifica ortografía y gramática, "
         "4. Utilizando el examen completo obtenido en el paso 2, corrige el examen completo para obtener las notas de cada pregunta"
         "5. Por último calcula la nota final."
         "Cuanto tengas la nota final, devuélvela como respuesta final y termina la conversación. No devuelvas nada más aparte de la nota final."
         "IMPORTANTE:"
         "1. No puedes usar herramientas que requieran el examen completo sin antes obtenerlo."
         "   Si no tienes los datos necesarios para una herramienta, debes llamar primero a otra herramienta para obtenerlos."
         "2. Devuelve siempre las listas en formato compacto, separadas por comas en una sola línea. No uses listas con guiones ni saltos de línea."),
        MessagesPlaceholder("messages")
    ])

    chat_llm = prompt_template | llm_with_tools

    # Chat node
    def chat_node(state: State) -> State:
        response = chat_llm.invoke({"messages": state["messages"]})
        state["messages"] = add_messages(
            state["messages"],
            response
        )
        
        return state

    # Tool node  
    async def tool_node(state: State, config: RunnableConfig | None) -> State:
        tool_node_instance = ToolNode(tools=tools)

        start_time = time.perf_counter()
        thread_id = config.get("configurable", {}).get("thread_id", "unknown_thread")

        # -------------------------
        # extraer tool REAL ejecutada
        # -------------------------
        last_message = state["messages"][-1]
        tool_name = "unknown"
        args_dict = {}

        if getattr(last_message, "tool_calls", None):
            tool_name = last_message.tool_calls[0].get("name", "unknown")
            args_dict = last_message.tool_calls[0].get("args", {})

        for attempt in range(3):
            try:
                # -------------------------
                # Ejecutar tools
                # -------------------------
                new_state = await tool_node_instance.ainvoke(
                    state,
                    config)

                duration_ms = int((time.perf_counter() - start_time) * 1000)

                # -------------------------
                # seguridad estructuras
                # -------------------------
                new_state.setdefault("last_tools_used", [])
                new_state.setdefault("tools_trace", [])
                new_state.setdefault("last_tool_results", [])

                # update last_tools_used
                new_state["last_tools_used"] = [tool_name]
                new_state["last_tool_results"] = [new_state["messages"][-1].content]

                # update tools_trace
                current_tools = state.get("tools_trace", [])
                new_state["tools_trace"] = [
                    *current_tools,
                    {
                        "tool": tool_name,
                        "args": args_dict
                    }
                ]

                # -------------------------
                # METRICS SUCCESS
                # -------------------------
                args_json = json.dumps(args_dict) if args_dict else None
                metrics.log_tool(
                    thread_id=thread_id,
                    tool_name=tool_name,
                    success=True,
                    duration_ms=duration_ms,
                    args=args_json
                )

                return new_state

            except Exception as e:
                duration_ms = int((time.perf_counter() - start_time) * 1000)

                # -------------------------
                # METRICS FAIL
                # -------------------------
                args_json = json.dumps(args_dict) if args_dict else None
                metrics.log_tool(
                    thread_id=thread_id,
                    tool_name=tool_name,
                    success=False,
                    duration_ms=duration_ms,
                    error=str(e),
                    args=args_json
                )

                state.setdefault("failed_tools", [])
                state["failed_tools"].append(tool_name)

                if attempt == 2:
                    return state
        
    async def control_node(state: State, config: RunnableConfig | None) -> State:
        thread_id = config.get("configurable", {}).get("thread_id", "unknown_thread")

        # -------------------------
        # safety init
        # -------------------------
        state.setdefault("route", "chat")
        state.setdefault("step_count", 0)
        state.setdefault("stuck_counter", 0)
        state.setdefault("tool_retries", {})
        state.setdefault("last_tools_used", [])
        state.setdefault("last_tool_signature", None)
        state.setdefault("tools_trace", [])
        state.setdefault("last_tool_results", [])

        # -------------------------
        # 1. step limit guard
        # -------------------------
        state["step_count"] += 1

        MAX_STEPS = 20

        if state["step_count"] >= MAX_STEPS:
            state["route"] = "end"
            metrics.log_workflow(
                f"{thread_id}",
                {
                    **state,
                    "reason": "max_steps_reached"
                }
            )
            return state

        # -------------------------
        # 2. detectar stuck (mejorado)
        # -------------------------
        current_signature = None

        if state["tools_trace"]:
            last_tool = state["tools_trace"][-1]
            current_signature = (
                last_tool.get("tool") + "|" +
                json.dumps(last_tool.get("args", {}), sort_keys=True)
            )

        # si no hay progreso o se repite exactamente la misma tool call
        if not current_signature:
            state["stuck_counter"] += 1
        elif current_signature == state.get("last_tool_signature"):
            state["stuck_counter"] += 1
        else:
            state["stuck_counter"] = 0

        state["last_tool_signature"] = current_signature

        # -------------------------
        # 4. REPLAN LOGIC
        # -------------------------
        if state["stuck_counter"] >= 3:
            state["route"] = "replan"

        # -------------------------
        # DEFAULT FLOW
        # -------------------------
        if state["route"] not in ["replan", "end"]:
            state["route"] = "chat"

        # -------------------------
        # log workflow metrics on replan or end
        # -------------------------
        #if state["route"] in ["replan", "end"]:
            metrics.log_workflow(
                f"{thread_id}",
                state
            )

        return state

    async def planner_node(state: State, config: RunnableConfig | None) -> State:
        thread_id = config.get("configurable", {}).get("thread_id", "unknown_thread")
        llm = ChatCohere(
            model="command-a-03-2025",
            temperature=0,
            cohere_api_key=settings.cohere_api_key
        )

        prompt = "Reformula el plan porque el anterior falló. Sé más simple."

        res = llm.invoke(prompt + str(state["messages"]))

        state["messages"] = add_messages(
            state["messages"],
            res
        )

        return state

    # Build graph
    graph = StateGraph(State)
    graph.add_node("chat_node", chat_node)
    graph.add_node("tool_node", tool_node)
    graph.add_node("control_node", control_node)
    graph.add_node("planner_node", planner_node)

    graph.add_edge(START, "chat_node")

    graph.add_conditional_edges(
        "chat_node",
        tools_condition,
        {
            "tools": "tool_node",
            "__end__": END
        }
    )

    graph.add_edge("tool_node", "control_node")

    graph.add_conditional_edges(
        "control_node",
        lambda state: state["route"],
        {
            "chat": "chat_node",
            "replan": "planner_node",
            "end": END
        }
    )
    
    graph.add_edge("planner_node", "chat_node")

    return graph.compile(debug=settings.langgraph_debug, checkpointer=checkpointer)


# ------------------------------
# Main loop
# ------------------------------

async def main():
    #tools, sessions = await load_all_mcp_tools()
    tools = await loadAllMcpServerTools()
    print(f"Tools loaded: {[t.name for t in tools]}")

    # create memory saver for checkpoints
    async with AsyncSqliteSaver.from_conn_string(settings.checkpoint_db_path) as checkpointer:
        agent = await create_graph(tools, checkpointer)

        session_manager = SessionManager()

        def read_batch_size() -> int:
            while True:
                value = input(
                    "\n¿Cuántos exámenes consecutivos quieres corregir desde el DNI 1? "
                    "(0 para omitir): "
                ).strip()
                try:
                    batch_size = int(value)
                except ValueError:
                    print("Introduce un número entero mayor o igual que 0.")
                    continue

                if batch_size < 0:
                    print("Introduce un número entero mayor o igual que 0.")
                    continue
                return batch_size

        async def process_prompt(user_input: str) -> None:
            try:
                thread_id = session_manager.get_thread()
                initial_state = {"messages": [HumanMessage(content=user_input)]}
                config = {"configurable": {"thread_id": thread_id}}
                response = await agent.ainvoke(initial_state, config=config)
                print("AI:", response["messages"][-1].content)

                #print("All Responses:", response["messages"][-1])
                #print("Herramientas utilizadas:", response["tools_trace"])
            except Exception as e:
                print("Error:", e)

        try:
            batch_size = read_batch_size()
            for student_id in range(1, batch_size + 1):
                user_input = (
                    "Corrige el examen de la asignatura bases de datos "
                    f"del estudiante con Dni {student_id} y nombre Jacobo Farray."
                )
                print(f"\nCorrigiendo examen del DNI {student_id}...")
                await process_prompt(user_input)

            while True:
                user_input = input("\nYou: ").strip()
                if user_input.lower() in {"exit", "quit", "q"}:
                    break

                await process_prompt(user_input)
        finally:
            print("An error ocurred, exiting.")

# Example usage:
"""
Corrige el examen de la asignatura Inteligencia Artificial del estudiante con Dni 1 y nombre Jacobo Farray.

Corrige el examen de la asignatura bases de datos del estudiante con Dni 1 y nombre Jacobo Farray.

Corrige ortográficamente el examen de la asignatura Inteligencia Artificial del estudiante con Dni 1 y nombre Jacobo Farray.

"""

# ------------------------------
# Run async main
# ------------------------------

if __name__ == "__main__":
    asyncio.run(main())
