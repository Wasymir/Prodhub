from typing import Annotated

from fastapi import APIRouter, Depends, status, Query, HTTPException
from psycopg import IntegrityError
from psycopg.rows import class_row, dict_row

import app.events
from app.database import Database
from app.products import products_router
from app.schemas import (
    TransactionSchema,
    TransactionQuery,
    CreateEventSchema,
    CreateTransactionSchema,
    UpdateTransaction,
)
from app.user import get_user_bearer, auth_resp, GetUserBearer
from app.utils import error_response, join_error_responses

transactions_router = APIRouter(
    prefix="/transactions",
    dependencies=[Depends(get_user_bearer)],
    tags=["Transactions"],
)

not_found_resp = {
    status.HTTP_404_NOT_FOUND: error_response(
        "Transaction with such id does not exist.", ["Such transaction does not exist"]
    )
}

not_enough_resp = {
    status.HTTP_409_CONFLICT: error_response(
        "Not enough product in stock.", ["Not enough product {product_id}"]
    )
}

not_found_err = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Such transaction does not exist"
)


@transactions_router.get(
    "/",
    response_model=list[TransactionSchema],
    status_code=status.HTTP_200_OK,
    responses=auth_resp,
)
async def get_all_transactions(
    body: Annotated[TransactionQuery, Query()], conn: Database
):
    async with conn.cursor(row_factory=class_row(TransactionQuery)) as cur:
        query = [
            'select transaction_id, "user", event, time, payment_method from get_all_transactions'
        ]
        args = []
        if body.start:
            query.append("where time > %s")
            args.append(body.start)
        if body.finish:
            query.append("where time < %s")
            args.append(body.finish)
        if body.user_id:
            query.append("where user_id = %s")
            args.append(body.user_id)
        if body.event_id:
            query.append("where event_id = %s")
            args.append(body.event_id)
        if body.payment_method:
            query.append("where payment_method = %s")
            args.append(body.payment_method)
        if body.order_by:
            match body.order_by:
                case "date":
                    query.append("order by date")
                case "sum":
                    query.append("order by sum")
        await cur.execute(" ".join(query), tuple(args))
        return await cur.fetchall()


@transactions_router.get(
    "/{transaction_id}",
    response_model=TransactionSchema,
    status_code=status.HTTP_200_OK,
    responses={**auth_resp, **not_found_resp},
)
async def get_transaction(transaction_id: int, conn: Database):
    async with conn.cursor(row_factory=class_row(TransactionSchema)) as cur:
        await cur.execute(
            'select transaction_id, "user", event, time, payment_method, sum, sales from get_all_transactions where transaction_id = %s',
            (transaction_id,),
        )
        if cur.rowcount == 0:
            raise not_found_err
        return await cur.fetchone()


@transactions_router.post(
    "/",
    response_model=TransactionSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        **auth_resp,
        **not_enough_resp,
        status.HTTP_404_NOT_FOUND: join_error_responses(
            app.events.not_found_resp, app.products.not_found_resp
        ),
    },
)
async def create_transaction(
    body: CreateTransactionSchema, user: GetUserBearer, conn: Database
):
    async with conn.cursor() as cur:
        try:
            for sale in body.sales:
                await cur.execute(
                    "update products set stock = stock - %s where product_id = %s",
                    (sale.amount, sale.product_id),
                )
                if cur.rowcount == 0:
                    raise app.products.not_found_err
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Not enough product {sale.product_id}",
            )

        try:
            await cur.execute(
                "insert into transactions(user_id, event_id, payment_method) values (%s, %s, %s) returning transaction_id",
                (user.user_id, body.event_id, body.payment_method),
            )
        except IntegrityError:
            raise app.events.not_found_err

        transaction_id = (await cur.fetchone())[0]

        for sale in body.sales:
            await cur.execute(
                """insert into sales (transaction_id, product_id, amount, price)
                values (
                    %s,
                    %s,
                    %s,
                    coalesce(%s, (select price from products where product_id = %s)))""",
                (
                    transaction_id,
                    sale.product_id,
                    sale.amount,
                    sale.price,
                    sale.product_id,
                ),
            )

    return await get_transaction(transaction_id, conn)


@transactions_router.delete(
    "/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **auth_resp,
        **not_found_resp,
    },
)
async def delete_transaction(
    transaction_id: int,
    conn: Database,
    return_products: bool = True,
):
    async with conn.cursor(row_factory=dict_row) as cur:
        await cur.execute(
            "delete from sales where transaction_id = %s returning product_id, amount",
            (transaction_id,),
        )
        if cur.rowcount == 0:
            raise not_found_err
        if return_products:
            data = await cur.fetchall()
            await cur.executemany(
                "update products set stock = stock + %(amount)s where product_id = %(product_id)s",
                data,
            )
        await cur.execute(
            "delete from transactions where transaction_id = %s", (transaction_id,)
        )


@transactions_router.patch(
    "/{transaction_id}",
    response_model=TransactionSchema,
    status_code=status.HTTP_200_OK,
    responses={
        **auth_resp,
        **not_enough_resp,
        status.HTTP_404_NOT_FOUND: join_error_responses(
            app.events.not_found_resp, app.products.not_found_resp
        ),
    },
)
async def update_transaction(
    transaction_id: int, body: UpdateTransaction, conn: Database, force: bool = False
):
    async with conn.cursor(row_factory=dict_row) as cur:
        try:
            await cur.execute(
                """update transactions set event_id = coalesce(%s, event_id), payment_method = coalesce(%s, payment_method) where transaction_id = %s""",
                (body.event_id, body.payment_method, transaction_id),
            )
        except IntegrityError:
            raise app.events.not_found_err

        if cur.rowcount == 0:
            raise not_found_err

        await cur.execute(
            "delete from sales where transaction_id = %s returning product_id, amount",
            (transaction_id,),
        )

        if not force:
            data = await cur.fetchall()
            await cur.executemany(
                "update products set stock = stock + %(amount)s where product_id = %(product_id)s",
                data,
            )

        try:
            for sale in body.sales:
                await cur.execute(
                    "update products set stock = stock - %s where product_id = %s",
                    (sale.amount, sale.product_id),
                )
                if cur.rowcount == 0:
                    raise app.products.not_found_err
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Not enough product {sale.product_id}",
            )

        for sale in body.sales:
            await cur.execute(
                """insert into sales (transaction_id, product_id, amount, price)
                values (
                    %s,
                    %s,
                    %s,
                    coalesce(%s, (select price from products where product_id = %s)))""",
                (
                    transaction_id,
                    sale.product_id,
                    sale.amount,
                    sale.price,
                    sale.product_id,
                ),
            )
    return await get_transaction(transaction_id, conn)
