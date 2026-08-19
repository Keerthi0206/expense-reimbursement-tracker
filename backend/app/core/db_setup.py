"""
Runs Alembic migrations programmatically. Used by both app.main (on server
startup) and seed.py (which can run standalone, before the server has ever
started) -- whichever runs first stamps the database at head, the other
sees it's already there and no-ops, since `alembic upgrade head` is
idempotent.
"""
import os


def run_migrations():
    from alembic import command
    from alembic.config import Config

    backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "migrations"))
    command.upgrade(alembic_cfg, "head")
