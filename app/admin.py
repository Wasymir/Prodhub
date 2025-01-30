import os
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, APIRouter, status
from fastapi.security import APIKeyHeader
from psycopg.errors import UniqueViolation
from psycopg.rows import class_row

from app.database import Database
from app.schemas import CreateUserSchema, UserSchema, UpdateUserSchema
from app.utils import hash_password

admin_auth = APIKeyHeader(name="x-admin-key")


def is_admin(api_key: Annotated[str, Depends(admin_auth)]):
    if not secrets.compare_digest(api_key.encode(), os.getenv("ADMIN_SECRET").encode()):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin Status Required"
        )


IsAdmin = Annotated[None, Depends(is_admin)]


admin_router = APIRouter(
    prefix="/admin", dependencies=[Depends(is_admin)], tags=["Admin Utils"]
)


@admin_router.post(
    "/users", response_model=UserSchema, status_code=status.HTTP_201_CREATED
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
                status_code=status.HTTP_409_CONFLICT, detail="Such User Already Exists"
            )

        user = await cur.fetchone()
    return user


@admin_router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: int, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute("delete from users where user_id = %s", (user_id,))
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Such User Does not Exist"
            )


@admin_router.patch(
    "/users/{user_id}", response_model=UserSchema, status_code=status.HTTP_200_OK
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
                detail="User with Such Username Already Exists",
            )

        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Such User Does not Exist"
            )
        user = await cur.fetchone()
    return user
