# Test settings — override Redis cache to avoid requiring a Redis server during tests
from project.settings import *  # noqa: F403

CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

SESSION_ENGINE = 'django.contrib.sessions.backends.db'
