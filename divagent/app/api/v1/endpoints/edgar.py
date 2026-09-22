from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.edgar import EdgarEnrichResult, EdgarRefreshResult
from app.services.edgar_loader import enrich_edgar, load_edgar

router = APIRouter(prefix="/edgar", tags=["edgar"])


@router.post("/refresh", response_model=EdgarRefreshResult)
async def refresh_edgar(session: AsyncSession = Depends(get_session)):
    """Fetch SEC EDGAR's company_tickers_exchange.json and upsert the
    NYSE + Nasdaq rows (cik, ticker, name, exchange) into the `edgar` table.
    """
    counts = await load_edgar(session)
    return EdgarRefreshResult(
        nasdaq_rows=counts["Nasdaq"],
        nyse_rows=counts["NYSE"],
        total_rows=counts["Nasdaq"] + counts["NYSE"],
    )


@router.post("/enrich", response_model=EdgarEnrichResult)
async def enrich_edgar_endpoint(session: AsyncSession = Depends(get_session)):
    """Enrich the `edgar` table with market cap: shares outstanding from EDGAR
    XBRL (per CIK) × the previous trading day's close from Polygon (per ticker).

    Manual, run ~twice a year after /edgar/refresh. Requires POLYGON_API_KEY.
    """
    counts = await enrich_edgar(session)
    return EdgarEnrichResult(
        total_rows=counts["total"],
        with_shares=counts["with_shares"],
        with_price=counts["with_price"],
        with_market_cap=counts["with_mktcap"],
    )
