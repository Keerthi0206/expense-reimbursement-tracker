"""
Shared test config. conftest.py loads before any test_*.py file, so this is
where env vars for the test DB need to be set -- app.core.database reads
DATABASE_URL once at import time, so setting it per-file too late does nothing.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"
os.environ["UPLOAD_DIR"] = "./test_suite_uploads"

import shutil

import pytest

from app.core.database import Base, engine


@pytest.fixture(scope="session", autouse=True)
def _test_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    if os.path.exists("./test_suite.db"):
        os.remove("./test_suite.db")
    if os.path.isdir("./test_suite_uploads"):
        shutil.rmtree("./test_suite_uploads", ignore_errors=True)
