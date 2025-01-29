from http import HTTPStatus

from fastapi import APIRouter, Depends, HTTPException
from psycopg.errors import UniqueViolation
from psycopg.rows import class_row

from app.database import Database
from app.schemas import CategorySchema, CreateUpdateCategory
from app.user import get_user_bearer

categories_router = APIRouter(
    prefix="/categories", dependencies=[Depends(get_user_bearer)], tags=["Categories"]
)


@categories_router.get(
    "/", response_model=list[CategorySchema], status_code=HTTPStatus.OK
)
async def get_all_categories(conn: Database):
    async with conn.cursor(row_factory=class_row(CategorySchema)) as cur:
        await cur.execute("select category_id, name from categories")
        return await cur.fetchall()


@categories_router.get(
    "/{category_id}", response_model=CategorySchema, status_code=HTTPStatus.OK
)
async def get_category(category_id: int, conn: Database):
    async with conn.cursor(row_factory=class_row(CategorySchema)) as cur:
        await cur.execute(
            "select category_id, name from categories where category_id = %s",
            (category_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="Such Category Does not Exist"
            )
        category = await cur.fetchone()
    return category


@categories_router.post(
    "/", response_model=CategorySchema, status_code=HTTPStatus.CREATED
)
async def create_category(body: CreateUpdateCategory, conn: Database):
    async with conn.cursor(row_factory=class_row(CategorySchema)) as cur:
        try:
            await cur.execute(
                "insert into categories (name) values (%s) returning category_id, name",
                (body.name,),
            )
        except UniqueViolation:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT, detail="Such Category Already Exists"
            )
        category = await cur.fetchone()
    return category


@categories_router.delete("/{category_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_category(category_id: int, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute(
            "delete from categories where category_id = %s", (category_id,)
        )
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="Such Category Does not Exist"
            )


@categories_router.patch(
    "/{category_id}", response_model=CategorySchema, status_code=HTTPStatus.OK
)
async def update_category(category_id: int, body: CreateUpdateCategory, conn: Database):
    async with conn.cursor(row_factory=class_row(CategorySchema)) as cur:
        try:
            await cur.execute(
                "update categories set name = %s where category_id = %s returning category_id, name",
                (body.name, category_id),
            )
        except UniqueViolation:
            raise HTTPException(
                status_code=HTTPStatus.CONFLICT, detail="Such Category Already Exists"
            )
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="Such Category Does not Exist"
            )
        category = await cur.fetchone()
    return category
