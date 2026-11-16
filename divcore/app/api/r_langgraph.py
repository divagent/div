from fastapi import APIRouter
from langgraph.graph import END, StateGraph

from app.langgraph.nodes_div import extract_with_llm, fetch_declared
from app.schemas.lg_state import ResolutionState, ResolveRequest  #state

langgraphRou = APIRouter()


# Graph
def build_graph():
    g = StateGraph(ResolutionState)
    g.add_node("fetch_declared", fetch_declared)
    g.add_node("extract_with_llm", extract_with_llm)

    g.set_entry_point("fetch_declared")
    g.add_edge("fetch_declared", "extract_with_llm")
    g.add_edge("extract_with_llm", END)

    return g.compile()

graph = build_graph()



@langgraphRou.post("/lg/resolve-declared", tags=["LangGraph"])
async def resolve_declared(req: ResolveRequest):
    initial_state: ResolutionState = {
        "ticker": req.ticker,
        "target_ex_date": req.target_ex_date,
        "raw_html": None,
        "candidate_amount": None,
        "candidate_date": None,
        "verified": False,
        "sources_tried": [],
        "stop_reason": None,
    }

    result = await graph.ainvoke(initial_state)
    return result 