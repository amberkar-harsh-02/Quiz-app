import pytest

import main
import models
from conftest import auth_header, make_user


# --- who can manage staff ---

@pytest.mark.parametrize("who", ["professor", "student"])
def test_only_admins_can_manage_staff(client, request, who):
    user = request.getfixturevalue(who)
    headers = auth_header(user)
    assert client.get("/staff", headers=headers).status_code == 403
    assert client.post("/staff", json={"email": "ta@csumb.edu"}, headers=headers).status_code == 403
    assert client.delete("/staff/prof@csumb.edu", headers=headers).status_code == 403


def test_list_staff(client, admin, professor):
    res = client.get("/staff", headers=auth_header(admin))

    assert res.status_code == 200
    body = res.json()
    assert body["admins"] == ["admin@csumb.edu"]
    assert [s["email"] for s in body["staff"]] == ["prof@csumb.edu"]
    assert body["staff"][0]["signed_up"] is True


# --- adding ---

def test_add_email_before_sign_up_then_sign_up_gets_access(client, db, admin):
    res = client.post("/staff", json={"email": " TA@csumb.edu "}, headers=auth_header(admin))
    assert res.status_code == 201
    assert res.json() == {"email": "ta@csumb.edu", "signed_up": False}

    listed = client.get("/staff", headers=auth_header(admin)).json()["staff"]
    assert {"email": "ta@csumb.edu", "signed_up": False, "added_by": "admin@csumb.edu"}.items() <= next(
        s for s in listed if s["email"] == "ta@csumb.edu").items()

    signup = client.post("/register", json={"email": "ta@csumb.edu", "password": "longenough1"})
    assert signup.json()["is_professor"] is True


def test_adding_existing_user_gives_access_immediately(client, db, admin, student):
    assert client.get("/quizzes/", headers=auth_header(student)).status_code == 403

    client.post("/staff", json={"email": "student@csumb.edu"}, headers=auth_header(admin))

    # Same old token, no new sign-in: the server checks the database on every request
    assert client.get("/quizzes/", headers=auth_header(student)).status_code == 200
    assert client.get("/me", headers=auth_header(student)).json()["is_professor"] is True


@pytest.mark.parametrize("email,status", [
    ("ta@gmail.com", 400),
    ("admin@csumb.edu", 400),
    ("prof@csumb.edu", 409),
])
def test_add_rejects_bad_or_duplicate_emails(client, admin, professor, email, status):
    res = client.post("/staff", json={"email": email}, headers=auth_header(admin))
    assert res.status_code == status


# --- removing ---

def test_removing_staff_takes_access_away_immediately(client, db, admin, professor):
    assert client.get("/quizzes/", headers=auth_header(professor)).status_code == 200

    res = client.delete("/staff/PROF@csumb.edu", headers=auth_header(admin))

    assert res.status_code == 200
    assert client.get("/quizzes/", headers=auth_header(professor)).status_code == 403
    assert db.query(models.StaffEmail).filter_by(email="prof@csumb.edu").count() == 0


def test_cannot_remove_admin_or_unknown_email(client, admin):
    assert client.delete("/staff/admin@csumb.edu", headers=auth_header(admin)).status_code == 400
    assert client.delete("/staff/nobody@csumb.edu", headers=auth_header(admin)).status_code == 404


def test_removed_professor_keeps_their_quizzes(client, db, admin, professor):
    db.add(models.Quiz(title="Mine", owner_id=professor.id))
    db.commit()
    client.delete("/staff/prof@csumb.edu", headers=auth_header(admin))
    assert db.query(models.Quiz).filter_by(owner_id=professor.id).count() == 1


# --- carrying over existing access ---

def test_seed_copies_existing_professors_and_legacy_emails(db, monkeypatch):
    user = models.User(email="oldprof@csumb.edu", hashed_password="x", is_professor=True)
    db.add(user)
    db.commit()
    monkeypatch.setattr(main, "LEGACY_PROFESSOR_EMAILS", {"pending@csumb.edu"})
    monkeypatch.setattr(main, "ADMIN_EMAILS", {"admin@csumb.edu"})

    main.seed_staff_emails()
    main.seed_staff_emails()  # safe to run on every startup

    emails = sorted(row.email for row in db.query(models.StaffEmail).all())
    assert emails == ["oldprof@csumb.edu", "pending@csumb.edu"]


def test_admin_added_to_settings_later_can_host_without_signing_in_again(client, db, student, monkeypatch):
    # An existing student account, still signed in, whose email is then put in ADMIN_EMAILS
    monkeypatch.setattr(main, "ADMIN_EMAILS", {"student@csumb.edu"})

    assert client.get("/me", headers=auth_header(student)).json() == {
        "email": "student@csumb.edu", "is_professor": True, "is_admin": True,
    }
    assert client.get("/quizzes/", headers=auth_header(student)).status_code == 200
    assert client.get("/staff", headers=auth_header(student)).status_code == 200
