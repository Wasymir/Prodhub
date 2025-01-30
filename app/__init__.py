import asyncio
import os

from dotenv import load_dotenv

if os.getenv("NO_ENV_FILE") != "true":
    load_dotenv()

if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
