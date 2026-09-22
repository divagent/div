# db.py
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.config import get_settings_singleton
settings = get_settings_singleton()

async_engine = create_async_engine(settings.DIV_AIVEN_ADMIN, pool_pre_ping=True,echo=False, )

async def get_db() -> AsyncGenerator[AsyncConnection, None]:
    async with async_engine.begin() as conn:
        yield conn
        
