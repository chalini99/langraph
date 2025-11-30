from typing import TypedDict, Annotated, Optional
from langgraph.graph import add_messages, StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessageChunk, ToolMessage
from dotenv import load_dotenv
from langchain_community.tools.tavily_search import TavilySearchResults
from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import json
from uuid import uuid4
from langgraph.checkpoint.memory import MemorySaver
import os

load_dotenv()

# Initialize memory saver
memory = MemorySaver()

class State(TypedDict):
    messages: Annotated[list, add_messages]

# SEARCH TOOL
search_tool = TavilySearchResults(max_results=4)
tools = [search_tool]

# LLM SETUP (FIXED)
llm_with_tools = ChatGroq(
    model="llama-3.1-8b-instant",
    api_key=os.getenv("GROQ_API_KEY"),
    temperature=0.3
).bind_tools([search_tool])



# MODEL NODE
async def model(state: State):
    result = await llm_with_tools.ainvoke(state["messages"])
    return {"messages": [result]}

# CONTROLLER FOR TOOL CALLS
async def tools_router(state: State):
    last_message = state["messages"][-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tool_node"
    return END

# TOOL EXECUTION NODE
async def tool_node(state):
    tool_calls = state["messages"][-1].tool_calls
    tool_messages = []

    for call in tool_calls:
        tool_name = call["name"]
        tool_args = call["args"]
        tool_id = call["id"]

        if tool_name == "tavily_search_results_json":
            search_results = await search_tool.ainvoke(tool_args)

            tool_messages.append(
                ToolMessage(
                    content=json.dumps(search_results),
                    tool_call_id=tool_id,
                    name=tool_name
                )
            )

    return {"messages": tool_messages}

# BUILD GRAPH
graph_builder = StateGraph(State)
graph_builder.add_node("model", model)
graph_builder.add_node("tool_node", tool_node)
graph_builder.set_entry_point("model")
graph_builder.add_conditional_edges("model", tools_router)
graph_builder.add_edge("tool_node", "model")
graph = graph_builder.compile(checkpointer=memory)

# FASTAPI APP
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def serialise_ai_message_chunk(chunk):
    if isinstance(chunk, AIMessageChunk):
        return chunk.content
    raise TypeError(f"Bad chunk type: {type(chunk)}")

# Generate SSE stream
async def generate_chat_responses(message: str, checkpoint_id: Optional[str] = None):
    is_new = checkpoint_id is None

    if is_new:
        new_id = str(uuid4())
        config = {"configurable": {"thread_id": new_id}}
        events = graph.astream_events({"messages": [HumanMessage(content=message)]}, version="v2", config=config)

        yield f"data: {{\"type\": \"checkpoint\", \"checkpoint_id\": \"{new_id}\"}}\n\n"
    else:
        config = {"configurable": {"thread_id": checkpoint_id}}
        events = graph.astream_events({"messages": [HumanMessage(content=message)]}, version="v2", config=config)

    async for event in events:
        event_type = event["event"]

        if event_type == "on_chat_model_stream":
            chunk = serialise_ai_message_chunk(event["data"]["chunk"]).replace("\n", "\\n").replace('"', '\\"')
            yield f"data: {{\"type\": \"content\", \"content\": \"{chunk}\"}}\n\n"

        elif event_type == "on_chat_model_end":
            yield "data: {\"type\": \"end\"}\n\n"

    yield "data: {\"type\": \"end\"}\n\n"


@app.get("/chat_stream/{message}")
async def chat_stream(message: str, checkpoint_id: Optional[str] = Query(None)):
    return StreamingResponse(generate_chat_responses(message, checkpoint_id), media_type="text/event-stream")
