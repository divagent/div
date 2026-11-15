from typing import Optional, TypedDict

from pydantic import BaseModel


class ResolutionState(TypedDict):
    ticker: str
    target_ex_date: str        # "2024-12-15" approximate
    candidate_amount: Optional[float]
    candidate_date: Optional[str]
    verified: bool
    sources_tried: list[str]
    stop_reason: Optional[str]


class ResolveRequest(BaseModel):
    ticker: str
    target_ex_date: str