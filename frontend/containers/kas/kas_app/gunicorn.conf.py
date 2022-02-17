"""
Auto-configure Gunicorn

Enables transfer of environment variables set in the Dockerfile to local
variables in the gunicorn module, because gunicorn runs this conf file
internally as part of its setup. So, to set the local gunicorn variable:

  ssl_version = 2

put this in the Docker file:

  ENV GUNICORN_SSL_VERSION 2

or this in a bash shell:

  $ export GUNICORN_SSL_VERSION = 2

Ref: sebest.github.io/post/protips-using-gunicorn-inside-a-docker-image
"""

import os
import sys

for k, v in os.environ.items():
    if k.startswith("GUNICORN_"):
        key = k.split("_", 1)[1].lower()
        locals()[key] = v

formatter = "json"
if os.environ.get("JSON_LOGGER", "").lower() == "false":
    formatter = "dev"


def env_level(env):
    lev = os.environ.get("LOGLEVEL", "NOTSET").upper()
    good = lev in [
        "CRITICAL",
        "ERROR",
        "WARNING",
        "INFO",
        "DEBUG",
        "NOTSET",
    ]
    if not good:
        print(f"Invalid log level (Non pythonic) [{env}='{lev}']", file=sys.stderr)
        return "NOTSET"
    return lev


app_level = env_level("LOGLEVEL")


logconfig_dict = {
    "version": 1,
    "formatters": {
        "dev": {
            "format": "[%(levelname)s] (%(name)s %(module)s:%(lineno)s) %(message)s",
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(levelname)s %(module)s %(lineno)s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": formatter,
        },
    },
    "loggers": {
        "gunicorn.error": {
            "level": "NOTSET",
            "propagate": 1,
        },
        "gunicorn.access": {
            "level": "NOTSET",
            "propagate": 1,
        },
        "tdf3_kas_app": {
            "level": app_level,
        },
        "tdf3_kas_core": {
            "level": app_level,
        },
    },
    "root": {"level": "INFO", "handlers": ["console"]},
}
