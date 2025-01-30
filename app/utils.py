import logging
import secrets
from hashlib import pbkdf2_hmac

from fastapi import APIRouter

logger = logging.getLogger("uvicorn.error")


def hash_password(password: str, salt: bytes | None = None) -> (bytes, bytes):
    """
    Hashes a password to a 256-byte digest with a salt. If the salt is not provided, a new one is randomly generated.

    :param password: The plaintext password to hash.
    :param salt: A 32-byte salt to use for hashing. If None, a random salt is generated.
    :return: A tuple containing the password digest and the salt.
    """
    if salt is None:
        salt = secrets.token_bytes(32)
    digest = pbkdf2_hmac("sha256", password.encode(), salt, 500_000, dklen=256)
    return digest, salt


def error_response(description: str, details: list[str]) -> dict:
    """
    Generates an OpenAPI response object for an error response caused by HTTPException.

    :param description: A human-readable description of the error.
    :param details: Literal values that `detail` can take.
    :return: A dictionary representing the OpenAPI response schema.
    """
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["detail"],
                    "properties": {
                        "detail": {"type": "string", "enum": details},
                    },
                },
            },
        },
    }
