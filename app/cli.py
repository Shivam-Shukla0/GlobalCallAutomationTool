"""Custom flask CLI commands: create admin, load scripts."""
import json
import os

import click
from flask import Flask

from .extensions import db
from .models import User


def register_cli(app: Flask) -> None:
    @app.cli.command("create-admin")
    def create_admin():
        """Create the bootstrap admin from ADMIN_USERNAME / ADMIN_PASSWORD."""
        username = os.environ.get("ADMIN_USERNAME", "admin")
        password = os.environ.get("ADMIN_PASSWORD")
        if not password:
            raise click.ClickException("Set ADMIN_PASSWORD in the environment first.")
        if db.session.scalar(db.select(User).filter_by(username=username)):
            click.echo(f"User '{username}' already exists.")
            return
        user = User(username=username, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Created admin '{username}'.")
