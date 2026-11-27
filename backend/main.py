"""Django ASGI launcher for local run and cloud hosting."""

from pathlib import Path
import os

from dotenv import load_dotenv
import uvicorn


load_dotenv(Path(__file__).resolve().with_name(".env"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fridge_service.settings")


def get_runtime_setting(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value or default


def get_runtime_flag(name: str, default: bool) -> bool:
    value = os.getenv(name, "").strip().lower()
    if not value:
        return default
    return value in ("1", "true", "yes", "on")


def get_runtime_port() -> int:
    try:
        return int(get_runtime_setting("PORT", "8000"))
    except ValueError:
        return 8000


if __name__ == "__main__":
    uvicorn.run(
        "fridge_service.asgi:application",
        host=get_runtime_setting("HOST", "0.0.0.0"),
        port=get_runtime_port(),
        reload=get_runtime_flag("UVICORN_RELOAD", True),
        log_level=get_runtime_setting("LOG_LEVEL", "info"),
    )
