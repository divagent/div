from divcore.app.api.r_langgraph import langgraphRou
from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from app.api.r_div import divRou
from app.api.r_market import marketRou
from app.api.r_trace import traceRou

rou = APIRouter()

rou.include_router(divRou)
rou.include_router(traceRou)
rou.include_router(marketRou)
rou.include_router(langgraphRou)


@rou.get("/")
def rouGet():
    return RedirectResponse(url="http://localhost:5173")
