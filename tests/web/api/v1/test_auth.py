from fastapi.testclient import TestClient

BASE_PATH = '/api/v1/auth/'


def test_login(app: TestClient, test_user):
    request = {
        'email': test_user.EMAIL,
        'password': test_user.PASSWORD
    }
    response = app.post(BASE_PATH + 'login', json=request)
    assert response.status_code == 200
    assert 'expired_at' in response.json().keys()


def test_login_invalid_payload(app: TestClient):
    response = app.post(BASE_PATH + 'login', {'foo': 'bar'})
    assert response.status_code == 422


def test_login_invalid_password(app: TestClient, test_user):
    request = {
        'email': test_user.EMAIL,
        'password': 'foobarfoobar'
    }
    response = app.post(BASE_PATH + 'login', json=request)
    assert response.status_code == 400


def test_register(app: TestClient, drop_users_after_test):
    request = {
        "email": 'Harkonnen.v@mail.com',
        "password": 'death_for_atreides!',
        "first_name": 'Vladimir',
        "last_name": 'Harkonnen'
    }
    response = app.post(BASE_PATH + 'register', json=request)
    assert response.status_code == 201


def test_register_invalid_payload(app: TestClient, drop_users_after_test):
    request = {
        "email": 'Harkonnen.v@mail.com',
        "password": 'death_for_atreides!',
    }
    response = app.post(BASE_PATH + 'register', json=request)
    assert response.status_code == 422


def test_register_email_already_exists(app: TestClient, test_user,
                                       drop_users_after_test):
    request = {
        "email": 'Harkonnen.v@mail.com',
        "password": 'death_for_atreides!',
    }
    response = app.post(BASE_PATH + 'register', json=request)
    assert response.status_code == 422