from pydantic import BaseModel


class EdgarRefreshResult(BaseModel):
    status: str = "ok"
    nasdaq_rows: int
    nyse_rows: int
    total_rows: int


class EdgarEnrichResult(BaseModel):
    status: str = "ok"
    total_rows: int
    with_shares: int
    with_price: int
    with_market_cap: int
