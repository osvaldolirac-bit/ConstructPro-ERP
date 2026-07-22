"""WSGI entrypoint for gunicorn."""

from rmweb.app import create_app

app = create_app()
