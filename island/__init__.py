"""Cloud Island for Windows."""
__version__ = "0.9.2"
APP_NAME = "Nelviro"
from .build_config import PUBLIC_RELEASE_REPOSITORY
REPOSITORY = PUBLIC_RELEASE_REPOSITORY or "BochkaPiva/dinamic_island_windows"
REPO_URL = f"https://github.com/{REPOSITORY}"
