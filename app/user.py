import secrets
from datetime import timedelta, datetime
from http import HTTPStatus
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import (
    HTTPBasic,
    HTTPBasicCredentials,
    HTTPBearer,
    HTTPAuthorizationCredentials,
)
from psycopg.errors import UniqueViolation
from psycopg.rows import class_row

from app.database import Database
from app.schemas import UserSchema, TokenSchema, UserWithTokenSchema
from app.utils import hash_password

user_router = APIRouter(prefix="/user", tags=["User Utils"])

basic_auth = HTTPBasic()


async def get_user_basic(
    credentials: Annotated[HTTPBasicCredentials, Depends(basic_auth)],
    conn: Database,
):
    async with conn.cursor(binary=True) as cur:
        await cur.execute(
            "select (user_id, password, salt) from users where username = %s",
            (credentials.username,),
        )
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Username or Password",
            )
        user_id, password, salt = (await cur.fetchone())[0]
        digest, _ = hash_password(credentials.password, salt)
        if not secrets.compare_digest(digest, password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Username or Password",
            )

        return UserSchema(user_id=user_id, username=credentials.username)


GetUserBasic = Annotated[UserSchema, Depends(get_user_basic)]


@user_router.post("/login", response_model=TokenSchema, status_code=HTTPStatus.CREATED)
async def login_user(user: GetUserBasic, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute(
            "select count(*) from tokens where user_id = %s", (user.user_id,)
        )
        if (await cur.fetchone())[0] > 5:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Token Limit Exceeded"
            )

        cur.row_factory = class_row(TokenSchema)
        expires = datetime.now() + timedelta(hours=10)
        while True:
            value = secrets.token_hex(32)
            try:
                await cur.execute(
                    "insert into tokens (user_id, value, expires)  values (%s, %s, %s) returning value, expires",
                    (user.user_id, value, expires),
                )
            except UniqueViolation:
                continue
            finally:
                token = await cur.fetchone()
                break

    return token


token_bearer = HTTPBearer()


async def get_user_bearer(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(token_bearer)],
    conn: Database,
):
    async with conn.cursor(row_factory=class_row(UserWithTokenSchema)) as cur:
        await cur.execute(
            """select u.user_id, u.username, t.value, t.expires from users u 
                inner join tokens t on u.user_id = t.user_id
                where t.value = %s and t.expires > now()""",
            (credentials.credentials,),
        )
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Invalid Token"
            )
        user = await cur.fetchone()
    return user


GetUserBearer = Annotated[UserWithTokenSchema, Depends(get_user_bearer)]


@user_router.get(
    "/", response_model=UserWithTokenSchema, status_code=status.HTTP_200_OK
)
async def get_user(user: GetUserBearer):
    return user


@user_router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: GetUserBearer, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute("delete from tokens where value = %s", (user.value,))


@user_router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(user: GetUserBearer, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute("delete from tokens where user_id = %s", (user.user_id,))
