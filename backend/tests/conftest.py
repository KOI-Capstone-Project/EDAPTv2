import asyncio
import pytest


@pytest.fixture(scope="session")
def event_loop():
    """Share one event loop across all tests so asyncpg connections stay valid."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
