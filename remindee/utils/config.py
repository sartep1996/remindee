import os
from pathlib import Path
from dotenv import load_dotenv
import platformdirs

load_dotenv()

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
APP_SECRET_KEY = os.getenv("APP_SECRET_KEY", "remindee-default-secret")

_data_dir = Path(platformdirs.user_data_dir("remindee", "remindee"))
_data_dir.mkdir(parents=True, exist_ok=True)

_default_db = _data_dir / "remindee.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite:///{_default_db}")
