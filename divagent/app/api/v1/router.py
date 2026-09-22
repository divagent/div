from fastapi import APIRouter

from app.api.v1.endpoints import edgar, market, symbols, trace

api_router = APIRouter()
api_router.include_router(symbols.router)
api_router.include_router(edgar.router)
api_router.include_router(trace.router)
api_router.include_router(market.router)
