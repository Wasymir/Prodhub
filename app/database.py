import os
from typing import Annotated

from fastapi import Depends
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool

db_pool = AsyncConnectionPool(os.getenv("DATABASE_URL"), open=False)


async def get_conn():
    async with db_pool.connection() as conn:
        yield conn


Database = Annotated[AsyncConnection, Depends(get_conn)]
