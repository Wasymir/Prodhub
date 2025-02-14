from typing import Annotated

from fastapi import APIRouter, Depends, Query, HTTPException, status
from psycopg.errors import UniqueViolation
from psycopg.rows import class_row

from app.database import Database
from app.schemas import (
    EventSchema,
    EventQuery,
    CreateEventSchema,
    UpdateEventSchema,
)
from app.user import get_user_bearer, auth_resp
from app.utils import error_response

events_router = APIRouter(
    prefix="/events", dependencies=[Depends(get_user_bearer)], tags=["Events"]
)

not_found_resp = {
    status.HTTP_404_NOT_FOUND: error_response(
        "Event with such id does not exist.", ["Event not found"]
    )
}

unique_violation_resp = {
    status.HTTP_409_CONFLICT: error_response(
        "Event with such name already exists.", ["Such event already exists"]
    )
}

not_found_err = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Event not found"
)

unique_violation_err = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Event with such name already exists",
)


@events_router.get(
    "/",
    response_model=list[EventSchema],
    status_code=status.HTTP_200_OK,
    responses=auth_resp,
)
async def get_all_events(data: Annotated[EventQuery, Query()], conn: Database):
    async with conn.cursor(row_factory=class_row(EventSchema)) as cur:
        query = ["select event_id, name, start, finish from events"]
        args = []
        if data.start:
            query.append("where start > %s")
            args.append(data.start)

        if data.finish:
            query.append("where finish < %s")
            args.append(data.finish)

        if data.filter:
            match data.filter:
                case "future":
                    query.append("where start > now()")
                case "past":
                    query.append("where finish < now()")
                case "ongoing":
                    query.append("where now() between start and finish")

        if data.order_by:
            query.append("order by %s")
            args.append(data.order_by)

        await cur.execute(" ".join(query), tuple(args))
        return await cur.fetchall()


@events_router.get(
    "/{event_id}",
    response_model=EventSchema,
    status_code=status.HTTP_200_OK,
    responses={
        **auth_resp,
        **not_found_resp,
    },
)
async def get_event(event_id: int, conn: Database):
    async with conn.cursor(row_factory=class_row(EventSchema)) as cur:
        await cur.execute(
            "select event_id, name, start, finish from events where event_id = %s",
            (event_id,),
        )
        if cur.rowcount == 0:
            raise not_found_err
        return await cur.fetchone()


@events_router.post(
    "/",
    response_model=EventSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        **auth_resp,
        **unique_violation_resp,
    },
)
async def create_event(body: CreateEventSchema, conn: Database):
    async with conn.cursor(row_factory=class_row(EventSchema)) as cur:
        try:
            await cur.execute(
                """insert into events (name, start, finish)
                values (%s, %s, %s)
                returning event_id, name, start, finish""",
                (body.name, body.start, body.finish),
            )
        except UniqueViolation:
            raise unique_violation_err

        return await cur.fetchone()


@events_router.delete(
    "/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **auth_resp,
        **not_found_resp,
    },
)
async def delete_event(event_id: int, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute("delete from events where event_id = %s", (event_id,))
        if cur.rowcount == 0:
            raise not_found_err


@events_router.patch(
    "/{event_id}",
    response_model=EventSchema,
    status_code=status.HTTP_200_OK,
    responses={**auth_resp, **not_found_resp, **unique_violation_resp},
)
async def update_event(event_id: int, body: UpdateEventSchema, conn: Database):
    async with conn.cursor(row_factory=class_row(EventSchema)) as cur:
        try:
            await cur.execute(
                """update events set
                name = coalesce(%s, name),
                start = coalesce(%s, start),
                finish = coalesce(%s, finish)
                where event_id = %s
                returning event_id, name, start, finish""",
                (body.name, body.start, body.finish, event_id),
            )
        except UniqueViolation:
            raise unique_violation_err
        if cur.rowcount == 0:
            raise not_found_err

        return await cur.fetchone()
