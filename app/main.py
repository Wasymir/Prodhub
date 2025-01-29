import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.admin import admin_router
from app.categories import categories_router
from app.database import db_pool
from app.products import products_router
from app.user import user_router
from app.utils import logger

tags_metadata = [
    {"name": "Admin Utils", "description": "Endpoints reserved for admin interface."},
    {"name": "User Utils", "description": "Session management endpoints for users."},
    {"name": "Categories", "description": "Endpoints for managing categories"},
    {"name": "Products", "description": "Endpoints for managing Products"},
]


@asynccontextmanager
async def lifespan(_: FastAPI):
    await db_pool.open()
    logger.info("Successfully opened connection pool.")
    yield
    await db_pool.close()
    logger.info("Successfully closed connection pool.")


app = FastAPI(
    title="ProdHub API",
    version="0.1.0-dev",
    openapi_tags=tags_metadata,
    lifespan=lifespan,
)

app.include_router(admin_router)

app.include_router(user_router)

app.include_router(categories_router)

app.include_router(products_router)

app.mount("/static", StaticFiles(directory="static"))


if __name__ == "__main__":
    uvicorn.run("app.main:app", host=os.getenv("HOST"), port=int(os.getenv("PORT")))
