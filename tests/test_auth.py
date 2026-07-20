def test_dashboard_requires_login(client):
    res = client.get("/")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]


def test_login_then_dashboard(auth_client):
    res = auth_client.get("/")
    assert res.status_code == 200


def test_bad_password_rejected(client):
    res = client.post("/login", data={"username": "tester", "password": "wrong"})
    assert b"Invalid username or password" in res.data


def test_health(client):
    assert client.get("/healthz").status_code == 200
