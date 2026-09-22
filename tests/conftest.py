import os
from pathlib import Path

TEST_DB = Path("/tmp/proyecto130-test.db")
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["API_KEY"] = ""
