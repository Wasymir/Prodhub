from datetime import datetime
from typing import Literal, Annotated

from pydantic import BaseModel, Field, ValidationInfo, AfterValidator


class UserSchema(BaseModel):
    user_id: int
    username: str


class CreateUserSchema(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=64)


class UpdateUserSchema(BaseModel):
    username: str | None = Field(None, min_length=1, max_length=64)
    password: str | None = Field(None, min_length=8, max_length=64)


class TokenSchema(BaseModel):
    value: str
    expires: datetime


class UserWithTokenSchema(UserSchema, TokenSchema):
    pass


class CategorySchema(BaseModel):
    category_id: int
    name: str


class CreateUpdateCategory(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class ProductSchema(BaseModel):
    product_id: int
    name: str = Field(min_length=1, max_length=128)
    stock: int = Field(ge=0)
    price: float = Field(ge=0)
    image: str | None = None
    categories: list[CategorySchema]


class CreateProductSchema(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    stock: int = Field(ge=0)
    price: float = Field(ge=0)
    categories: list[int]


class UpdateProductSchema(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=128)
    stock: int | None = Field(None, ge=0)
    price: float | None = Field(None, ge=0)
    categories: list[int] | None = None


class EventSchema(BaseModel):
    event_id: int
    name: str
    start: datetime | None = None
    finish: datetime | None = None


def check_end_not_before_start(finish: datetime, info: ValidationInfo) -> datetime:
    if "start" in info.data:
        if finish and info.data["start"] and finish < info.data["start"]:
            raise ValueError("Finish time cannot be before start time")
        return finish
    return finish


class EventQuery(BaseModel):
    start: datetime | None = Field(default=None)
    finish: Annotated[datetime | None, AfterValidator(check_end_not_before_start)] = (
        None
    )
    filter: Literal["future", "past", "ongoing"] | None = None
    order_by: Literal["name", "start", "finish"] | None = None


class CreateEventSchema(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    start: datetime | None = None
    finish: Annotated[datetime | None, AfterValidator(check_end_not_before_start)] = (
        None
    )


class UpdateEventSchema(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    start: datetime | None = Field(default=None)
    finish: Annotated[datetime | None, AfterValidator(check_end_not_before_start)] = (
        None
    )


class SaleSchema(BaseModel):
    sale_id: int
    product: ProductSchema | None = None
    amount: int
    price: float


class CreateSaleSchema(BaseModel):
    product_id: int
    amount: int
    price: float | None = None


PaymentMethod = Literal["Cash", "Card", "BLIK"]


class TransactionSchema(BaseModel):
    transaction_id: int
    user: UserSchema
    event: EventSchema | None = None
    time: datetime
    payment_method: PaymentMethod
    sales: list[SaleSchema]


class TransactionQuery(BaseModel):
    start: datetime | None = None
    finish: Annotated[datetime | None, AfterValidator(check_end_not_before_start)] = (
        None
    )
    user_id: int | None = None
    event_id: int | None = None
    payment_method: PaymentMethod | None = None
    order_by: Literal["date", "sum"] | None = None


class CreateTransactionSchema(BaseModel):
    event_id: int | None = None
    payment_method: PaymentMethod
    sales: list[CreateSaleSchema]


class UpdateTransaction(BaseModel):
    event_id: int | None = None
    payment_method: PaymentMethod | None = None
    sales: list[CreateSaleSchema] | None = None
