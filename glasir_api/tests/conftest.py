import sys
import os
import time # Import time for sleep

# Add project root to sys.path to allow imports like 'from glasir_api...'
# This assumes pytest is run from the project root directory
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
    print(f"Added project root to sys.path: {project_root}")
import pytest
import pytest_asyncio
import os
from typing import AsyncGenerator, Generator, Any
from unittest.mock import patch, AsyncMock # Import mock utilities

# Database imports
import databases
import sqlalchemy # Needed for metadata
from alembic.config import Config
from alembic import command

# Import Base from your models
from glasir_api.models.db_models import Base
# Metadata will be accessed via Base.metadata

import httpx
from fastapi import FastAPI
from dotenv import load_dotenv

# Load test environment variables BEFORE importing the app
# Ensure this runs early enough. A session-scoped autouse fixture is suitable.
@pytest.fixture(scope="session", autouse=True)
def load_test_env():
    """Loads environment variables from .env.test for the test session."""
    env_path = os.path.join(os.path.dirname(__file__), '..', '.env.test')
    load_dotenv(dotenv_path=env_path, override=True)
    # Set an environment variable to signal test mode if needed by the app
    os.environ["TESTING"] = "true"
    print(f"Loaded test environment from: {env_path}")
    print(f"DATABASE_URL set to: {os.getenv('DATABASE_URL')}") # Verify loading

# Import the app AFTER loading the test environment
# This ensures the app initializes with the test DATABASE_URL
from glasir_api.main import app as main_app

@pytest.fixture(scope="session")
def anyio_backend():
    """Use asyncio backend for pytest-asyncio."""
    return "asyncio"

# Determine paths relative to conftest.py
TEST_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(TEST_DIR, '..')) # Go up one level from tests/
ALEMBIC_INI_PATH = os.path.join(PROJECT_ROOT, 'alembic.ini')
TEST_DB_FILENAME = "test_glasir_data.db" # Defined in .env.test
TEST_DB_PATH = os.path.join(PROJECT_ROOT, TEST_DB_FILENAME) # Absolute path to test DB

@pytest.fixture(scope="session")
def alembic_config() -> Config:
    """Provides the Alembic configuration object."""
    if not os.path.exists(ALEMBIC_INI_PATH):
        raise FileNotFoundError(f"Alembic config not found at: {ALEMBIC_INI_PATH}")
    config = Config(ALEMBIC_INI_PATH)
    # Point Alembic to the test database URL using the absolute path
    absolute_db_url = f"sqlite+aiosqlite:///{TEST_DB_PATH}?check_same_thread=False"
    config.set_main_option("sqlalchemy.url", absolute_db_url)
    print(f"Alembic config explicitly set sqlalchemy.url to absolute path: {absolute_db_url}")

    # Calculate and set the *absolute* path to the script directory
    project_root_cwd = os.getcwd() # Get current working directory (project root)
    alembic_script_path_abs = os.path.abspath(os.path.join(project_root_cwd, "glasir_api", "alembic"))
    config.set_main_option("script_location", alembic_script_path_abs)

    print(f"Alembic script location explicitly set to absolute path: {alembic_script_path_abs}")
    return config

@pytest_asyncio.fixture(scope="function")
async def app_with_db(mocker, alembic_config: Config) -> AsyncGenerator[FastAPI, None]:
    """
    Provides the FastAPI app instance with a connected database,
    a shared httpx client, and mocked rate limiter for testing.
    Ensures migrations are run for each test function *before* connecting.
    """
    # Use the absolute path for consistency
    db_url_absolute = f"sqlite+aiosqlite:///{TEST_DB_PATH}?check_same_thread=False"

    # --- Step 1: Ensure Clean DB State & Apply Migrations ---
    if os.path.exists(TEST_DB_PATH):
        print(f"[app_with_db] Removing existing test database file: {TEST_DB_PATH}")
        os.remove(TEST_DB_PATH)
    print("[app_with_db] Running Alembic upgrade head...")
    try:
        # Alembic uses the absolute path set in alembic_config
        command.upgrade(alembic_config, "head")
        print("[app_with_db] Alembic upgrade head completed.")
        # Add a small delay to allow filesystem changes to propagate
        time.sleep(0.1)
        print("[app_with_db] Short delay after Alembic upgrade.")
    except Exception as e:
        print(f"[app_with_db] Alembic upgrade failed: {e}")
        raise

    # --- Step 2: Setup App and Mocks ---
    test_app = main_app
    shared_http_client = None
    database = None

    # Mock Rate Limiter
    mocker.patch("fastapi_limiter.FastAPILimiter.init", return_value=None)
    async def mock_limiter_dependency(*args, **kwargs): pass
    mocker.patch("fastapi_limiter.depends.RateLimiter.__call__", side_effect=mock_limiter_dependency, create=True)
    print("Patched fastapi-limiter init and dependency call.")

    # Explicitly manage lifespan within the fixture
    # Patch os.getenv specifically for DATABASE_URL during lifespan startup
    # to ensure the app connects to the exact same DB file Alembic migrated.
    # Patch os.getenv within the main module specifically for DATABASE_URL during lifespan startup
    # to ensure the app connects to the exact same DB file Alembic migrated.
    with patch('glasir_api.main.os.getenv', side_effect=lambda key, default=None: db_url_absolute if key == "DATABASE_URL" else os.environ.get(key, default)):
        # Explicitly manage lifespan within the fixture
        async with test_app.router.lifespan_context(test_app):
            print(f"[app_with_db] Lifespan startup initiated with patched DATABASE_URL: {db_url_absolute}")
            print("[app_with_db] Lifespan startup complete. Yielding app instance.")
            yield test_app # Provide the app instance to the test client
            # Lifespan shutdown is handled automatically by the context manager exit
            print("[app_with_db] Lifespan shutdown complete.")

    # No separate finally block needed here as lifespan context handles cleanup
    print("[app_with_db] Fixture teardown complete.")


@pytest_asyncio.fixture(scope="function")
async def async_client(app_with_db: FastAPI) -> AsyncGenerator[httpx.AsyncClient, None]:
    """
    Provides an asynchronous test client for making requests to the app
    which has its database state correctly initialized by app_with_db.
    """
    async with httpx.AsyncClient(app=app_with_db, base_url="http://testserver") as client:
        print(f"Async client created for app: {app_with_db.title}")
        yield client
        print("Async client teardown.")

# Removed db_session fixture. Tests use app_with_db.state.database.