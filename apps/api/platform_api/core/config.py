from pathlib import Path
from pydantic import BaseModel


class Settings(BaseModel):
    package_storage_dir: Path = Path("var/packages")
    run_storage_dir: Path = Path("var/runs")
    metadata_db_path: Path = Path("var/platform.sqlite3")
    environment: str = "dev"


settings = Settings()
