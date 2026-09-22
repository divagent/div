from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.symbols import RefreshResult
from app.services.symbol_loader import refresh_all

router = APIRouter(prefix="/symbols", tags=["symbols"])


@router.post("/refresh", response_model=RefreshResult)
async def refresh_symbols(session: AsyncSession = Depends(get_session)):
    """Fetch the Nasdaq Trader symbol directories and reload both tables.

    - `nasdaq` <- nasdaqlisted.txt (all rows)
    - `nyse`   <- otherlisted.txt (Exchange == 'N' only)
    """
    nasdaq_rows, nyse_rows = await refresh_all(session)
    return RefreshResult(nasdaq_rows=nasdaq_rows, nyse_rows=nyse_rows)
