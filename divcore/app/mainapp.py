import os
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from starlette import status

from app.config import get_settings_singleton
from app.core.rag_middleware import request_context_middleware
from app.db.conn.db_async import async_engine
from app.api import rou

# setup_logger()
security = HTTPBasic()

def verify_auth(credentials: HTTPBasicCredentials = Depends(security)):
    settings = get_settings_singleton()
    admin_password = os.getenv("ADMIN_PASSWORD", settings.ADMIN_PASSWORD)
    if credentials.password != admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        async with async_engine.begin() as conn: pass
        yield
    finally:
        await async_engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings_singleton()
    
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        docs_url="/swagger",
        redoc_url="/swagger_redoc",
        dependencies=[Depends(verify_auth)],
        # lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        # allow_origins=settings.ALLOWED_ORIGINS,
        # allow_credentials=True,
        allow_origins=["*"],
        allow_credentials=False,  # MUST be False when origins="*"
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    app.middleware("http")(request_context_middleware)

    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "ok"}

    app.include_router(rou)

    return app
