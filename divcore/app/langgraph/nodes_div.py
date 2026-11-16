import json

import httpx

from app.adapters.LLM_Chat import chat_completion_agent_with_model
from app.schemas.lg_state import ResolutionState
from app.skills.extract_w_llm import EXTRACT_PROMPT


# Node1
async def fetch_declared(state:ResolutionState) -> dict:
    ticker = state["ticker"]
    url = f"https://dividendhistory.org/payout/{ticker}/"

    try: 
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
        found = resp.status_code==200
        raw_html = resp.text if resp.status_code == 200 else None
    except Exception: 
        found = False
        raw_html = None
    
    return {
        "sources_tried": state["sources_tried"] + ["dividendhistory.org"],
        "raw_html": raw_html,
        "stop_reason": None if found else "source_unreachable",
        "verfied": False,
    }


# Node2
async def extract_with_llm(state: ResolutionState)->dict:
    raw_html = state.get("raw_html", "")
    if not raw_html: 
        return {"stop_reason": "no html to extract"}

    try:
        text, model_label = await chat_completion_agent_with_model(
            messages=[
                {"role": "system", "content": EXTRACT_PROMPT},
                {"role": "user", "content": f"Ticker: {state['ticker']}\n\nHTML:\n{raw_html[:8000]}"},
            ]
        )
        data = json.loads(text)
        return {
            "candidate_amount": data.get("amount"),
            "candidate_date": data.get("ex_date"),
            "sources_tried": state["sources_tried"] + [f"llm:{model_label}"],
            "stop_reason": None if data.get("amount") else "extraction_failed",
        }
    except Exception as e:
        return {"stop_reason": f"llm_error:{e}"}