"""Bootstrap legacy SQLite schema for Django runtime."""

from __future__ import annotations

import asyncio
import os
import threading


_BOOTSTRAPPED = False
_LOCK = threading.Lock()


def _run_async_blocking(async_func) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(async_func())
        return

    error: list[BaseException] = []

    def runner() -> None:
        try:
            asyncio.run(async_func())
        except BaseException as exc:  # pragma: no cover - error is re-raised in caller thread
            error.append(exc)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()

    if error:
        raise error[0]


def ensure_legacy_schema() -> None:
    global _BOOTSTRAPPED
    if os.getenv("DJANGO_SKIP_LEGACY_BOOTSTRAP", "false").strip().lower() in ("1", "true", "yes", "on"):
        return

    with _LOCK:
        if _BOOTSTRAPPED:
            return
        from app.db.database import close_db, init_db

        _run_async_blocking(init_db)
        _run_async_blocking(close_db)
        _BOOTSTRAPPED = True