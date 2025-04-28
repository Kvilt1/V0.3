import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv
from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Add glasir_api directory to sys.path to find models
# Ensure this path calculation is robust
_root = os.path.realpath(os.path.join(os.path.dirname(__file__), '..'))
if _root not in sys.path:
    sys.path.insert(0, _root)
# load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env')) # REMOVED: Let tests handle environment loading

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
# from myapp import mymodel
# target_metadata = mymodel.Base.metadata
# target_metadata = None
from models.db_models import Base  # Import the Base class
target_metadata = Base.metadata # Assign metadata from Base

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get the database URL *from the Alembic config object first*
    # This ensures it uses the URL set programmatically (e.g., in tests)
    db_url = config.get_main_option("sqlalchemy.url")
    if not db_url:
        # Fallback to environment variable if not in config (shouldn't happen in tests)
        db_url = os.getenv('DATABASE_URL')
        if not db_url:
            raise ValueError("Database URL not found in Alembic config or DATABASE_URL environment variable.")
        print("Warning: Using DATABASE_URL from environment in env.py, not from Alembic config.")

    # Make the URL synchronous for Alembic's engine
    sync_db_url = db_url.replace("+aiosqlite", "")

    # Prepare configuration for engine_from_config, ensuring our URL is used
    configuration = config.get_section(config.config_ini_section, {})
    # configuration['sqlalchemy.url'] = sync_db_url # Ensure the correct, synchronous URL is used

    print(f"env.py: Creating synchronous engine for Alembic online migrations with URL: {sync_db_url}")
    # Manually create the engine
    connectable = create_engine(sync_db_url)

    # with connectable.connect() as connection:
    # The above context manager might close the connection too early for the transaction below.
    # Let's manage the connection manually within the transaction context.
    connection = connectable.connect()
    try:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        # Run migrations within a transaction
        with context.begin_transaction():
            print("env.py: Running migrations...")
            context.run_migrations()
            print("env.py: Migrations finished.")
    finally:
        # Ensure the connection is closed
        connection.close()
        print("env.py: Closed synchronous engine connection.")


if context.is_offline_mode():
    run_migrations_offline()
else:
    from sqlalchemy import create_engine # Add import here
    run_migrations_online()
