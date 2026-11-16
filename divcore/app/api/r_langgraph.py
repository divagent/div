import httpx
from fastapi import APIRouter
from langgraph.graph import END, StateGraph

from app.schemas.lg_state import ResolutionState, ResolveRequest  #state

langgraphRou = APIRouter()

# Nodes
async def fetch_declared(state:ResolutionState) -> dict:
    ticker = state["ticker"]
    url = f"https://dividendhistory.org/payout/{ticker}/"

    try: 
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
            found = resp.status_code==200
    except Exception: 
        found = False

    
    return {
        "sources_tried": state["sources_tried"] + ["dividendhistory.org"],
        "stop_reason": None if found else "source_unreachable",
        "verfied": False,
    }


# Graph
def build_graph():
    g = StateGraph(ResolutionState)
    g.add_node("fetch_declared", fetch_declared)
    g.set_entry_point("fetch_declared")
    g.add_edge("fetch_declared", END)
    return g.compile()

graph = build_graph()



@langgraphRou.post("/lg/resolve-declared", tags=["LangGraph"])
async def resolve_declared(req: ResolveRequest):
    initial_state: ResolutionState = {
        "ticker": req.ticker,
        "target_ex_date": req.target_ex_date,
        "candidate_amount": None,
        "candidate_date": None,
        "verified": False,
        "sources_tried": [],
        "stop_reason": None,
    }

    result = await graph.ainvoke(initial_state)
    return result 