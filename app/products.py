import os
from http import HTTPStatus
from io import BytesIO
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from fastapi import APIRouter, Depends, HTTPException, UploadFile
from psycopg.errors import UniqueViolation, IntegrityError
from psycopg.rows import class_row, dict_row

from app.database import Database
from app.schemas import (
    ProductSchema,
    CreateProductSchema,
    CategorySchema,
    UpdateProductSchema,
)
from app.user import get_user_bearer

products_router = APIRouter(
    prefix="/products", dependencies=[Depends(get_user_bearer)], tags=["Products"]
)


@products_router.get("/", response_model=list[ProductSchema], status_code=HTTPStatus.OK)
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
    "/{product_id}", response_model=ProductSchema, status_code=HTTPStatus.OK
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
                status_code=HTTPStatus.NOT_FOUND, detail="Such Product Does not Exist"
            )
        product = await cur.fetchone()
    return product


@products_router.post("/", response_model=ProductSchema, status_code=HTTPStatus.CREATED)
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
                status_code=HTTPStatus.CONFLICT, detail="Such Product Already Exists"
            )
        except IntegrityError:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="Such Category Does not Exist"
            )

    return product


@products_router.delete(
    "/{product_id}",
    status_code=HTTPStatus.NO_CONTENT,
)
async def delete_product(product_id: int, conn: Database):
    async with conn.cursor() as cur:
        await cur.execute("delete from products where product_id = %s", (product_id,))
        if cur.rowcount == 0:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="Such Product Does not Exist"
            )
    image = Path("static", f"{product_id}.png")
    if image.exists():
        os.remove(image)


@products_router.patch(
    "/{product_id}", response_model=ProductSchema, status_code=HTTPStatus.OK
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
                status_code=HTTPStatus.CONFLICT, detail="Such Product Already Exists"
            )

        if cur.rowcount == 0:
            raise HTTPException(
                status_code=HTTPStatus.NOT_FOUND, detail="Such Product Does not Exist"
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
                        status_code=HTTPStatus.NOT_FOUND,
                        detail="Such Product Does not Exist",
                    )
                case "category_id":
                    raise HTTPException(
                        status_code=HTTPStatus.NOT_FOUND,
                        detail="Such Category Does not Exist",
                    )

    return await get_product(product_id, conn)


@products_router.post(
    "{product_id}/image", response_model=ProductSchema, status_code=HTTPStatus.CREATED
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
                status_code=HTTPStatus.NOT_FOUND, detail="Such Product Does not Exist"
            )
        try:
            contests = await file.read()
            image = Image.open(BytesIO(contests))
            image.save(Path("static", f"{product_id}.png"))
        except UnidentifiedImageError:
            raise HTTPException(
                status_code=HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                detail="Unable to determine file type",
            )
    return await get_product(product_id, conn)


@products_router.delete(
    "/{product_id}/image",
    status_code=HTTPStatus.NO_CONTENT,
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
                status_code=HTTPStatus.NOT_FOUND, detail="Such Image Does not Exist"
            )


@products_router.patch(
    "/{product_id}/image",
    response_model=ProductSchema,
)
async def update_product_image(
    product_id: int, conn: Database, file: UploadFile | None = None
):
    if file is None:
        await delete_product_image(product_id, conn)
        return await get_product(product_id, conn)
    else:
        return await create_product_image(product_id, file, conn)
