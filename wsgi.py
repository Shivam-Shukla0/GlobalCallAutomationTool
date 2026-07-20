"""Gunicorn / flask entrypoint:  gunicorn wsgi:app"""
from app import create_app
from app.cli import register_cli

app = create_app()
register_cli(app)
