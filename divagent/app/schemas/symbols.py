from pydantic import BaseModel


class RefreshResult(BaseModel):
    status: str = "ok"
    nasdaq_rows: int
    nyse_rows: int
