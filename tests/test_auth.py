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
    res = client.post("/register", json={"email": "New.User@CSUMB.edu", "password": "longenough1"})

    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "new.user@csumb.edu"
    assert body["is_professor"] is False
    assert "password" not in body and "hashed_password" not in body
    stored = db.query(models.User).filter_by(email="new.user@csumb.edu").one()
    assert stored.hashed_password != "longenough1"


def test_register_rejects_non_csumb_email(client):
    res = client.post("/register", json={"email": "someone@gmail.com", "password": "longenough1"})
    assert res.status_code == 400
    assert "csumb.edu" in res.json()["detail"]


def test_register_rejects_duplicate_email_case_insensitive(client, student):
    res = client.post("/register", json={"email": "STUDENT@csumb.edu", "password": "longenough1"})
    assert res.status_code == 400
    assert res.json()["detail"] == "Email already registered."


def test_register_ignores_self_declared_professor_flag(client):
    res = client.post("/register", json={"email": "p@csumb.edu", "password": "longenough1", "is_professor": True})
    assert res.status_code == 200
    assert res.json()["is_professor"] is False


def test_register_rejects_short_password(client):
    res = client.post("/register", json={"email": "p@csumb.edu", "password": "short"})
    assert res.status_code == 422


def password_login(client, email, password="longenough1"):
    token = client.post("/token", data={"username": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_password_sign_up_with_a_staff_email_cannot_host(client, db):
    # Anyone could type a listed email; nothing proves it's theirs until they use Google
    db.add(models.StaffEmail(email="p@csumb.edu", added_by="admin@csumb.edu"))
    db.commit()
    client.post("/register", json={"email": "P@csumb.edu", "password": "longenough1"})
    headers = password_login(client, "p@csumb.edu")

    assert client.get("/quizzes/", headers=headers).status_code == 403
    assert client.get("/me", headers=headers).json() == {
        "email": "p@csumb.edu", "is_professor": False, "is_admin": False, "staff_needs_google": True,
    }


def test_password_sign_up_with_an_admin_email_cannot_manage_staff(client, monkeypatch):
    monkeypatch.setattr(main, "ADMIN_EMAILS", {"boss@csumb.edu"})
    client.post("/register", json={"email": "boss@csumb.edu", "password": "longenough1"})
    headers = password_login(client, "boss@csumb.edu")

    assert client.get("/staff", headers=headers).status_code == 403
    assert client.post("/staff", json={"email": "friend@csumb.edu"}, headers=headers).status_code == 403
    assert client.get("/quizzes/", headers=headers).status_code == 403


def test_login_syncs_role_with_staff_list(client, db, student, professor):
    db.add(models.StaffEmail(email="student@csumb.edu", added_by="admin@csumb.edu"))
    db.query(models.StaffEmail).filter_by(email="prof@csumb.edu").delete()
    db.commit()

    promoted = client.post("/token", data={"username": "student@csumb.edu", "password": "password123"})
    demoted = client.post("/token", data={"username": "prof@csumb.edu", "password": "password123"})

    decode = lambda res: jwt.decode(res.json()["access_token"], main.SECRET_KEY, algorithms=[main.ALGORITHM])
    assert decode(promoted)["is_professor"] is True
    assert decode(demoted)["is_professor"] is False
    db.refresh(student)
    db.refresh(professor)
    assert student.is_professor is True
    assert professor.is_professor is False


def test_login_token_marks_admins(client, admin):
    res = client.post("/token", data={"username": "admin@csumb.edu", "password": "password123"})
    payload = jwt.decode(res.json()["access_token"], main.SECRET_KEY, algorithms=[main.ALGORITHM])
    assert payload["is_admin"] is True
    assert payload["is_professor"] is True


# --- /me ---

def test_me_reports_current_role(client, db, student, admin):
    assert client.get("/me", headers=auth_header(student)).json() == {
        "email": "student@csumb.edu", "is_professor": False, "is_admin": False, "staff_needs_google": False,
    }
    assert client.get("/me", headers=auth_header(admin)).json()["is_admin"] is True


def test_me_requires_sign_in(client):
    assert client.get("/me").status_code == 401


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

def google_login(client, email, verified=True):
    claims = {"email": email, "email_verified": verified}
    with patch.object(main.id_token, "verify_oauth2_token", return_value=claims):
        return client.post("/google-login", json={"token": "fake"})


def test_google_login_creates_new_student(client, db):
    res = google_login(client, "GUser@csumb.edu")

    assert res.status_code == 200
    user = db.query(models.User).filter_by(email="guser@csumb.edu").one()
    assert user.is_professor is False
    assert user.email_verified is True
    assert user.hashed_password == "GOOGLE_SSO_USER"


def test_google_login_reuses_existing_user(client, db, professor):
    res = google_login(client, "prof@csumb.edu")

    assert res.status_code == 200
    assert db.query(models.User).count() == 1
    payload = jwt.decode(res.json()["access_token"], main.SECRET_KEY, algorithms=[main.ALGORITHM])
    assert payload["is_professor"] is True


def test_google_login_rejects_non_csumb_account(client, db):
    res = google_login(client, "x@gmail.com")

    assert res.status_code == 403
    assert db.query(models.User).count() == 0


def test_google_login_invalid_token_does_not_echo_library_error(client):
    with patch.object(main.id_token, "verify_oauth2_token", side_effect=ValueError("bad token details")):
        res = client.post("/google-login", json={"token": "fake"})

    assert res.status_code == 401
    assert res.json()["detail"] == "Google sign-in failed. Please try again."


@pytest.mark.parametrize("claims", [
    {"email": "x@csumb.edu", "email_verified": False},
    {"email": "x@csumb.edu"},
    {"email_verified": True},
])
def test_google_login_requires_a_verified_email(client, db, claims):
    with patch.object(main.id_token, "verify_oauth2_token", return_value=claims):
        res = client.post("/google-login", json={"token": "fake"})

    assert res.status_code in (401, 403)
    assert db.query(models.User).count() == 0


def test_google_login_refused_when_client_id_not_set(client, db, monkeypatch):
    # Google's library skips the audience check when it's None, accepting tokens made for other sites
    monkeypatch.setattr(main, "GOOGLE_CLIENT_ID", None)
    verify = patch.object(main.id_token, "verify_oauth2_token", return_value={"email": "x@csumb.edu", "email_verified": True})
    with verify as mocked:
        res = client.post("/google-login", json={"token": "fake"})

    assert res.status_code == 503
    mocked.assert_not_called()
    assert db.query(models.User).count() == 0


def test_google_login_takes_over_a_squatted_password_account(client, db):
    # Someone registered a staff member's email by password before they did
    db.add(models.StaffEmail(email="ta@csumb.edu", added_by="admin@csumb.edu"))
    db.commit()
    client.post("/register", json={"email": "ta@csumb.edu", "password": "squatter123"})

    res = google_login(client, "ta@csumb.edu")

    assert res.status_code == 200
    real_owner = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/quizzes/", headers=real_owner).status_code == 200
    # The squatter's password no longer works
    stale = client.post("/token", data={"username": "ta@csumb.edu", "password": "squatter123"})
    assert stale.status_code == 401
    assert stale.json()["detail"] == "This account uses Sign in with Google."


def test_student_password_account_becomes_google_only_after_google_sign_in(client, db):
    client.post("/register", json={"email": "kid@csumb.edu", "password": "longenough1"})
    google_login(client, "kid@csumb.edu")

    user = db.query(models.User).filter_by(email="kid@csumb.edu").one()
    assert user.email_verified is True
    assert client.post("/token", data={"username": "kid@csumb.edu", "password": "longenough1"}).status_code == 401


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
