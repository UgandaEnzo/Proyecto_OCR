import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# allow importing project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
fileConfig(config.config_file_name)

# Import target metadata from models
import models
target_metadata = models.Base.metadata

# If the ini file does not have sqlalchemy.url set, try to get from environment or database.py
from database import SQLALCHEMY_DATABASE_URL
if not config.get_main_option('sqlalchemy.url'):
    # Avoid configparser interpolation errors: escape percent signs
    raw_url = os.getenv('DATABASE_URL', SQLALCHEMY_DATABASE_URL)
    safe_url = raw_url.replace('%', '%%')
    config.set_main_option('sqlalchemy.url', safe_url)


def run_migrations_offline():
    url = config.get_main_option('sqlalchemy.url')
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
