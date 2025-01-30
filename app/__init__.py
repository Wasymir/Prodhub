import asyncio
import os

from dotenv import load_dotenv

if os.getenv("NO_ENV_FILE") != "true":
    load_dotenv()

expected_vars = ["DATABASE_URL", "HOST", "PORT", "ADMIN_SECRET"]

for var in expected_vars:
    if os.getenv(var) is None:
        raise RuntimeError(f"Expected '{var}' environment variable to be defined.")


if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
