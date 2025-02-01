from fastapi import APIRouter, Depends, HTTPException, status
from psycopg.errors import UniqueViolation
from psycopg.rows import class_row

from app.database import Database
from app.schemas import CategorySchema, CreateUpdateCategory
from app.user import get_user_bearer, auth_resp
from app.utils import error_response

categories_router = APIRouter(
    prefix="/categories", dependencies=[Depends(get_user_bearer)], tags=["Categories"]
)

not_found_resp = {
    status.HTTP_404_NOT_FOUND: error_response(
        "Category with such id does not exist.", ["Such category does not exist"]
    )
}

unique_violation_resp = {
    status.HTTP_409_CONFLICT: error_response(
        "Category with such name already exists.", ["Such category already exists"]
    )
}

not_found_err = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Such category does not exist",
)

unique_violation_err = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Such category already exists",
)


@categories_router.get(
    "/",
    response_model=list[CategorySchema],
    status_code=status.HTTP_200_OK,
    responses=auth_resp,
)
async def get_all_categories(conn: Database):
    async with conn.cursor(row_factory=class_row(CategorySchema)) as cur:
        await cur.execute("select category_id, name from categories")
        return await cur.fetchall()


@categories_router.get(
    "/{category_id}",
    response_model=CategorySchema,
    status_code=status.HTTP_200_OK,
    responses={
        **auth_resp,
        **not_found_resp,
    },
)
async def get_category(category_id: int, conn: Database):
    async with conn.cursor(row_factory=class_row(CategorySchema)) as cur:
        await cur.execute(
            "select category_id, name from categories where category_id = %s",
            (category_id,),
        )
        if cur.rowcount == 0:
            raise not_found_err
        return await cur.fetchone()


@categories_router.post(
    "/",
    response_model=CategorySchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        **auth_resp,
        **unique_violation_resp,
    },
)
async def create_category(body: CreateUpdateCategory, conn: Database):
    async with conn.cursor(row_factory=class_row(CategorySchema)) as cur:
        try:
            await cur.execute(
                "insert into categories (name) values (%s) returning category_id, name",
                (body.name,),
            )
        except UniqueViolation:
            raise unique_violation_err
        return await cur.fetchone()


@categories_router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={**auth_resp, **not_found_resp},
)
async def delete_category(category_id: int, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute(
            "delete from categories where category_id = %s", (category_id,)
        )
        if cur.rowcount == 0:
            raise not_found_err


@categories_router.patch(
    "/{category_id}",
    response_model=CategorySchema,
    status_code=status.HTTP_200_OK,
    responses={
        **auth_resp,
        **unique_violation_resp,
        **not_found_resp,
    },
)
async def update_category(category_id: int, body: CreateUpdateCategory, conn: Database):
    async with conn.cursor(row_factory=class_row(CategorySchema)) as cur:
        try:
            await cur.execute(
                "update categories set name = %s where category_id = %s returning category_id, name",
                (body.name, category_id),
            )
        except UniqueViolation:
            raise unique_violation_err
        if cur.rowcount == 0:
            raise not_found_err
        return await cur.fetchone()
