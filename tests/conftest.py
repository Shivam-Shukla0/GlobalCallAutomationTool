import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models import User


@pytest.fixture
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        db.create_all()
        user = User(username="tester", role="admin")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def auth_client(app, client):
    client.post("/login", data={"username": "tester", "password": "secret"})
    return client
