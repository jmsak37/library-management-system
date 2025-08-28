import dj_database_url
import os
from pathlib import Path
# ...

DATABASES['default'] = dj_database_url.config(conn_max_age=600, ssl_require=False)

# Static files (WhiteNoise recommended)
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "/static/"
