from datetime import datetime, timedelta
from unittest.mock import patch

import jwt
import pytest

import main
import models
from conftest import auth_header, make_user


# --- helpers ---

def test_password_hash_verifies_and_is_not_plaintext():
    hashed = main.get_password_hash("hunter2")
    assert hashed != "hunter2"
    assert main.pwd_context.verify("hunter2", hashed)
    assert not main.pwd_context.verify("wrong", hashed)


def test_create_access_token_contains_claims_and_expiry():
    token = main.create_access_token({"sub": "a@csumb.edu", "is_professor": True})
    payload = jwt.decode(token, main.SECRET_KEY, algorithms=[main.ALGORITHM])

    assert payload["sub"] == "a@csumb.edu"
    assert payload["is_professor"] is True
    expires_in = datetime.utcfromtimestamp(payload["exp"]) - datetime.utcnow()
    assert timedelta(hours=23) < expires_in <= timedelta(hours=24)


def test_create_access_token_does_not_mutate_input():
    data = {"sub": "a@csumb.edu"}
    main.create_access_token(data)
    assert data == {"sub": "a@csumb.edu"}


# --- /register ---

def test_register_success_lowercases_email(client, db):
    res = client.post("/register", json={"email": "New.User@CSUMB.edu", "password": "pw"})

    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "new.user@csumb.edu"
    assert body["is_professor"] is False
    assert "password" not in body and "hashed_password" not in body
    stored = db.query(models.User).filter_by(email="new.user@csumb.edu").one()
    assert stored.hashed_password != "pw"


def test_register_rejects_non_csumb_email(client):
    res = client.post("/register", json={"email": "someone@gmail.com", "password": "pw"})
    assert res.status_code == 400
    assert "csumb.edu" in res.json()["detail"]


def test_register_rejects_duplicate_email_case_insensitive(client, student):
    res = client.post("/register", json={"email": "STUDENT@csumb.edu", "password": "pw"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Email already registered."


def test_register_professor_flag(client):
    res = client.post("/register", json={"email": "p@csumb.edu", "password": "pw", "is_professor": True})
    assert res.json()["is_professor"] is True


# --- /token ---

def test_login_success_returns_bearer_token(client, professor):
    res = client.post("/token", data={"username": "PROF@csumb.edu", "password": "password123"})

    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    payload = jwt.decode(body["access_token"], main.SECRET_KEY, algorithms=[main.ALGORITHM])
    assert payload["sub"] == "prof@csumb.edu"
    assert payload["is_professor"] is True


@pytest.mark.parametrize("username,password", [
    ("prof@csumb.edu", "wrong-password"),
    ("nobody@csumb.edu", "password123"),
])
def test_login_failure(client, professor, username, password):
    res = client.post("/token", data={"username": username, "password": password})
    assert res.status_code == 401
    assert res.json()["detail"] == "Incorrect email or password"


# --- /google-login ---

def test_google_login_creates_new_student(client, db):
    with patch.object(main.id_token, "verify_oauth2_token", return_value={"email": "GUser@csumb.edu"}):
        res = client.post("/google-login", json={"token": "fake"})

    assert res.status_code == 200
    user = db.query(models.User).filter_by(email="guser@csumb.edu").one()
    assert user.is_professor is False
    assert user.hashed_password == "GOOGLE_SSO_USER"


def test_google_login_reuses_existing_user(client, db, professor):
    with patch.object(main.id_token, "verify_oauth2_token", return_value={"email": "prof@csumb.edu"}):
        res = client.post("/google-login", json={"token": "fake"})

    assert res.status_code == 200
    assert db.query(models.User).count() == 1
    payload = jwt.decode(res.json()["access_token"], main.SECRET_KEY, algorithms=[main.ALGORITHM])
    assert payload["is_professor"] is True


def test_google_login_rejects_non_csumb_account(client, db):
    with patch.object(main.id_token, "verify_oauth2_token", return_value={"email": "x@gmail.com"}):
        res = client.post("/google-login", json={"token": "fake"})

    assert res.status_code == 403
    assert db.query(models.User).count() == 0


def test_google_login_invalid_token(client):
    with patch.object(main.id_token, "verify_oauth2_token", side_effect=ValueError("bad token")):
        res = client.post("/google-login", json={"token": "fake"})

    assert res.status_code == 401
    assert "bad token" in res.json()["detail"]


# --- auth dependencies (exercised via a protected route) ---

def test_protected_route_requires_token(client):
    assert client.get("/quizzes/").status_code == 401


def test_protected_route_rejects_garbage_token(client):
    res = client.get("/quizzes/", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


def test_protected_route_rejects_token_signed_with_other_key(client, professor):
    token = jwt.encode({"sub": professor.email}, "some-other-key", algorithm="HS256")
    res = client.get("/quizzes/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_protected_route_rejects_expired_token(client, professor):
    token = jwt.encode(
        {"sub": professor.email, "exp": datetime.utcnow() - timedelta(minutes=1)},
        main.SECRET_KEY, algorithm=main.ALGORITHM,
    )
    res = client.get("/quizzes/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_protected_route_rejects_token_without_sub(client):
    token = main.create_access_token({"is_professor": True})
    res = client.get("/quizzes/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_protected_route_rejects_token_for_deleted_user(client):
    token = main.create_access_token({"sub": "ghost@csumb.edu", "is_professor": True})
    res = client.get("/quizzes/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_professor_route_forbids_students(client, student):
    res = client.get("/quizzes/", headers=auth_header(student))
    assert res.status_code == 403
    assert res.json()["detail"] == "Professors and TAs only."


def test_professor_flag_is_read_from_db_not_token(client, db):
    # A student forging is_professor=True in their token must still be rejected
    user = make_user(db, "sneaky@csumb.edu", is_professor=False)
    token = main.create_access_token({"sub": user.email, "is_professor": True})
    res = client.get("/quizzes/", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
