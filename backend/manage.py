#!/usr/bin/env python3
"""Django 管理入口。"""

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fridge_service.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()