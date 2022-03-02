"""This example file exposes a wsgi-callable object as app."""

import os

from wsgicors import CORS

from tdf3_kas_app import kas_app

app = CORS(
    kas_app.app(__name__),
    headers=str(
        os.environ.get(
            "WSGI_CORS_HEADERS",
            "Origin, X-Requested-With, Content-Type, Authorization, X-Session-Id, X-Virtru-Client, X-No-Redirect, Virtru-Ntdf-Version",
        )
    ),
    methods=str(
        os.environ.get("WSGI_CORS_METHODS", "GET, POST, PUT, PATCH, OPTIONS, DELETE")
    ),
    maxage=str(os.environ.get("WSGI_CORS_MAX_AGE", 180)),
    origin=str(os.environ.get("WSGI_CORS_ORIGIN", "https://localhost")),
)
