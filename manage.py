#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DEPS = os.path.join(BASE_DIR, ".deps")

if os.path.isdir(LOCAL_DEPS) and LOCAL_DEPS not in sys.path:
    sys.path.insert(0, LOCAL_DEPS)


def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == '__main__':
    main()
