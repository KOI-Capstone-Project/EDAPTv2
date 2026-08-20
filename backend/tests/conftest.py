import asyncio

import pytest

from app.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Share one event loop across all tests so asyncpg connections stay valid."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
def run_app_startup(event_loop):
    """Run the app's real startup handler once before any test.

    httpx's ASGITransport does NOT trigger FastAPI startup events — it calls the
    ASGI app directly, skipping the lifespan protocol. `_startup()` is what
    creates the tables (Base.metadata.create_all) and seeds the default users,
    so without this every database-touching test fails on a database that
    doesn't already happen to be initialised.

    This was a REAL failure, not a hypothetical one: the suite passed locally
    for the whole project's history only because the dev Postgres had already
    been set up by the separate long-running uvicorn container. Against the
    clean Postgres service container in CI it failed 21 of 31 tests with
    `sqlalchemy.exc.ProgrammingError: relation "users" does not exist`. The
    tests were depending on state created by another process — the same class
    of problem as the shap container-drift incident, in the database layer.

    Calls the application's own startup handler rather than a test-local copy of
    create_all + seeding, so tests initialise through exactly the code path
    production uses and the two cannot drift apart.
    """
    event_loop.run_until_complete(app.router.startup())
    yield
