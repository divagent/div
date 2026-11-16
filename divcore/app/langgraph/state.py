from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional, TypedDict

from app.schemas.sch_ai import JWType
from sqlalchemy.ext.asyncio import AsyncSession


class Agent2State(TypedDict, total=False):
    query: str
    top_k: int
    zjwt: JWType
    db: AsyncSession
    status_cb: Callable[[str, Dict[str, Any]], Awaitable[None] | None]
    route: str
    decision: Dict[str, Any]
    route_reasoning: List[str]
    rag_response: Dict[str, Any]
    sql_text: str
    sql_rationale: Optional[str]
    sql_reasoning: List[str]
    general_payload: Dict[str, Any]
    general_reasoning: List[str]
    response: Dict[str, Any]
