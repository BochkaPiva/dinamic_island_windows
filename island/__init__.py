"""Cloud Island for Windows."""
__version__ = "0.7.1"
APP_NAME = "Cloud Island"
from .build_config import PUBLIC_RELEASE_REPOSITORY
REPOSITORY = PUBLIC_RELEASE_REPOSITORY or "BochkaPiva/dinamic_island_windows"
REPO_URL = f"https://github.com/{REPOSITORY}"
