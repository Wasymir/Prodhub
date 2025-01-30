import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, APIRouter, status
from fastapi.security import APIKeyHeader
from psycopg.errors import UniqueViolation
from psycopg.rows import class_row

from app.database import Database
from app.schemas import CreateUserSchema, UserSchema, UpdateUserSchema
from app.utils import hash_password, error_response

admin_auth = APIKeyHeader(name="x-admin-key")


def is_admin(api_key: Annotated[str, Depends(admin_auth)]):
    if not secrets.compare_digest(api_key.encode(), os.getenv("ADMIN_SECRET").encode()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin status required"
        )


IsAdmin = Annotated[None, Depends(is_admin)]


admin_router = APIRouter(
    prefix="/admin", dependencies=[Depends(is_admin)], tags=["Admin Utils"]
)

auth_resp = {
    status.HTTP_403_FORBIDDEN: error_response(
        "Invalid admin key", ["Admin status required"]
    )
}

unique_violation_resp = {
    status.HTTP_409_CONFLICT: error_response(
        "User with such username already exists.", ["Such user already exists"]
    )
}

not_found_resp = {
    status.HTTP_404_NOT_FOUND: error_response(
        "User with such id does not exist. ", ["Such user does not exist."]
    )
}


@admin_router.post(
    "/users",
    response_model=UserSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        **auth_resp,
        **unique_violation_resp,
    },
)
async def create_user(body: CreateUserSchema, conn: Database):
    password, salt = hash_password(body.password)
    async with conn.cursor(row_factory=class_row(UserSchema)) as cur:
        try:
            await cur.execute(
                "INSERT INTO users (username, salt, password) VALUES (%s, %s, %s) RETURNING user_id, username",
                (body.username, salt, password),
            )
        except UniqueViolation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Such user already exists"
            )

        user = await cur.fetchone()
    return user


@admin_router.delete(
    "/users/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **auth_resp,
        **not_found_resp,
    },
)
async def delete_user(user_id: int, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute("delete from users where user_id = %s", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Such user does not exist"
            )


@admin_router.patch(
    "/users/{user_id}",
    response_model=UserSchema,
    status_code=status.HTTP_200_OK,
    responses={
        **auth_resp,
        **unique_violation_resp,
        **not_found_resp,
    },
)
async def update_user(body: UpdateUserSchema, user_id: int, conn: Database):
    password, salt = None, None
    if body.password:
        password, salt = hash_password(body.password)
    async with conn.cursor(row_factory=class_row(UserSchema)) as cur:
        try:
            await cur.execute(
                """update users
                    set username = coalesce(%s, username), password = coalesce(%s, password), salt = coalesce(%s, salt)
                    where user_id = %s
                    returning user_id, username""",
                (body.username, password, salt, user_id),
            )

        except UniqueViolation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Such user already exist",
            )

        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Such user does not exist"
            )
        user = await cur.fetchone()
    return user
