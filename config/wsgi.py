"""
WSGI config for config project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/wsgi/
"""

import os
import sys
from pathlib import Path

from django.core.wsgi import get_wsgi_application

BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_DEPS = BASE_DIR / ".deps"

if LOCAL_DEPS.is_dir():
    sys.path.insert(0, str(LOCAL_DEPS))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

application = get_wsgi_application()
