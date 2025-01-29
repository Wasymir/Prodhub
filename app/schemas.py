from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserSchema(BaseModel):
    user_id: int
    username: str


class CreateUserSchema(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=64)


class UpdateUserSchema(BaseModel):
    username: Optional[str] = Field(None, min_length=1, max_length=64)
    password: Optional[str] = Field(None, min_length=8, max_length=64)


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
    image: str | None = Field(default=None)
    categories: list[CategorySchema]


class CreateProductSchema(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    stock: int = Field(ge=0)
    price: float = Field(ge=0)
    categories: list[int]


class UpdateProductSchema(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=128)
    stock: Optional[int] = Field(default=None, ge=0)
    price: Optional[float] = Field(default=None, ge=0)
    categories: Optional[list[int]] = None
