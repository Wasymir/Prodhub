import os
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from psycopg.errors import UniqueViolation, IntegrityError
from psycopg.rows import class_row, dict_row

import app.categories
from app.database import Database
from app.schemas import (
    ProductSchema,
    CreateProductSchema,
    CategorySchema,
    UpdateProductSchema,
)
from app.user import get_user_bearer, auth_resp
from app.utils import error_response, get_responses

products_router = APIRouter(
    prefix="/products", dependencies=[Depends(get_user_bearer)], tags=["Products"]
)

not_found_resp = {
    status.HTTP_404_NOT_FOUND: error_response(
        "Product with such id does not exist.", ["Such product does not exist"]
    )
}

unique_violation_resp = {
    status.HTTP_409_CONFLICT: error_response(
        "Product with such name already exists.", ["Such product already exists"]
    )
}

invalid_image_resp = {
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: error_response(
        "Invalid image data.", ["Unable to determine image format"]
    )
}


@products_router.get(
    "/", response_model=list[ProductSchema], status_code=status.HTTP_200_OK
)
async def get_all_products(conn: Database):
    async with conn.cursor(row_factory=class_row(ProductSchema)) as cur:
        await cur.execute("""select 
            p.product_id, 
            p.name, 
            p.stock, 
            p.price, 
            p.image,
            coalesce(
                json_agg(
                    json_build_object(
                        'category_id', c.category_id, 
                        'name', c.name
                    )
                ) filter (where c.category_id is not null), '[]'::json
            ) as categories
        from products p
        left join product_categories pc on p.product_id = pc.product_id
        left join categories c on pc.category_id = c.category_id
        group by p.product_id;""")
        products = await cur.fetchall()
    return products


@products_router.get(
    "/{product_id}",
    response_model=ProductSchema,
    status_code=status.HTTP_200_OK,
    responses={
        **auth_resp,
        **not_found_resp,
    },
)
async def get_product(product_id: int, conn: Database):
    async with conn.cursor(row_factory=class_row(ProductSchema)) as cur:
        await cur.execute(
            """select 
            p.product_id, 
            p.name, 
            p.stock, 
            p.price, 
            p.image,
            coalesce(
                json_agg(
                    json_build_object(
                        'category_id', c.category_id, 
                        'name', c.name
                    )
                ) filter (where c.category_id is not null), '[]'::json
            ) as categories
        from products p
        left join product_categories pc on p.product_id = pc.product_id
        left join categories c on pc.category_id = c.category_id
        where p.product_id = %s
        group by p.product_id;""",
            (product_id,),
        )
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Such product does not exist",
            )
        product = await cur.fetchone()
    return product


@products_router.post(
    "/",
    response_model=ProductSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        **auth_resp,
        **unique_violation_resp,
        **app.categories.not_found_resp,
    },
)
async def create_product(body: CreateProductSchema, conn: Database):
    async with conn.cursor(row_factory=dict_row) as cur:
        try:
            await cur.execute(
                "insert into products (name, stock, price) values (%s, %s, %s) RETURNING product_id, name, stock, price",
                (body.name, body.stock, body.price),
            )
            partial = await cur.fetchone()
            data = [
                (partial["product_id"], category_id) for category_id in body.categories
            ]
            await cur.executemany(
                "insert into product_categories (product_id, category_id) values (%s, %s)",
                data,
            )
            cur.row_factory = class_row(CategorySchema)
            await cur.execute(
                "select c.category_id, c.name from categories c join product_categories pc on c.category_id = pc.category_id where pc.product_id = %s",
                (partial["product_id"],),
            )
            categories = await cur.fetchall()
            product = ProductSchema(**partial, categories=categories)

        except UniqueViolation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Such product already exists",
            )
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Such category does not exist",
            )

    return product


@products_router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **auth_resp,
        **not_found_resp,
    },
)
async def delete_product(product_id: int, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute("delete from products where product_id = %s", (product_id,))
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Such product does not exist",
            )
    image = Path("static", f"{product_id}.png")
    if image.exists():
        os.remove(image)


@products_router.patch(
    "/{product_id}",
    response_model=ProductSchema,
    status_code=status.HTTP_200_OK,
    responses={
        **auth_resp,
        **unique_violation_resp,
        status.HTTP_404_NOT_FOUND: error_response(
            "Either product or category with such id does not exist.",
            ["Such product does not exist", "Such category does not exist"],
        ),
    },
)
async def update_product(body: UpdateProductSchema, product_id: int, conn: Database):
    async with conn.cursor() as cur:
        try:
            await cur.execute(
                """update products set
                name = coalesce(%s, name),
                stock = coalesce(%s, stock),
                price = coalesce(%s, price)
                where product_id = %s""",
                (body.name, body.stock, body.price, product_id),
            )
        except UniqueViolation:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Such product already exists",
            )

        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Such product does not exist",
            )

        if body.categories is None:
            return await get_product(product_id, conn)

        await cur.execute(
            "delete from product_categories where not (product_id = any (%s))",
            (body.categories,),
        )

        try:
            data = [(product_id, category_id) for category_id in body.categories]
            await cur.executemany(
                "insert into product_categories (product_id, category_id) values (%s, %s) on conflict do nothing",
                data,
            )
        except IntegrityError as e:
            match e.diag.column_name:
                case "product_id":
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Such product does not exist",
                    )
                case "category_id":
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="Such category does not exist",
                    )

    return await get_product(product_id, conn)


@products_router.post(
    "{product_id}/image",
    response_model=ProductSchema,
    status_code=status.HTTP_201_CREATED,
    responses={
        **auth_resp,
        **not_found_resp,
        **invalid_image_resp,
    },
)
async def create_product_image(product_id: int, file: UploadFile, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute(
            "update products set image = %s where product_id = %s",
            (
                f"{os.getenv('HOST')}:{os.getenv('PORT')}/static/{product_id}.png",
                product_id,
            ),
        )
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Such product does not exist",
            )
        try:
            contests = await file.read()
            image = Image.open(BytesIO(contests))
            image.save(Path("static", f"{product_id}.png"))
        except UnidentifiedImageError:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="Unable to determine image type",
            )
    return await get_product(product_id, conn)


@products_router.delete(
    "/{product_id}/image",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        **auth_resp,
        status.HTTP_404_NOT_FOUND: error_response(
            "There isn't an image associated with such product id.",
            ["Such image does not exist"],
        ),
    },
)
async def delete_product_image(product_id: int, conn: Database):
    async with conn.cursor() as cur:
        path = Path("static", f"{product_id}.png")
        if path.exists():
            os.remove(path)
            await cur.execute(
                "update products set image = null where product_id = %s",
                (product_id,),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Such image does not exist",
            )


@products_router.patch(
    "/{product_id}/image",
    response_model=ProductSchema,
    status_code=status.HTTP_200_OK,
    description="A wrapper around other product image related endpoints. Expect the same return codes as in them.",
)
async def update_product_image(
    product_id: int, conn: Database, file: UploadFile | None = None
):
    if file is None:
        await delete_product_image(product_id, conn)
        return await get_product(product_id, conn)
    else:
        return await create_product_image(product_id, file, conn)
