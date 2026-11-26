"""The operator tool that vouches for accounts from the server (for addresses that aren't Google accounts)."""
import pytest

import main
import models
import verify_email
from conftest import make_user


@pytest.fixture(autouse=True)
def no_real_env(monkeypatch):
    # The tool reads ADMIN_EMAILS from .env; tests decide it instead
    monkeypatch.setattr(verify_email, "admin_emails", lambda: {"legend@csumb.edu"})


def answers(*replies):
    replies = iter(replies)
    return lambda prompt: next(replies)


def sign_in(client, email, password):
    return client.post("/token", data={"username": email, "password": password})


def test_vouching_restores_admin_rights_to_a_password_account(client, db, monkeypatch, capsys):
    monkeypatch.setattr(main, "ADMIN_EMAILS", {"legend@csumb.edu", "dnegel@csumb.edu"})
    for email in ("legend@csumb.edu", "dnegel@csumb.edu"):
        make_user(db, email, password="madeup123", email_verified=False)
    token = sign_in(client, "legend@csumb.edu", "madeup123").json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/staff", headers=headers).status_code == 403

    assert verify_email.main(["legend@csumb.edu", "DNEGEL@csumb.edu"]) == 0

    # Same password, same token: the server checks the database on every request
    assert client.get("/staff", headers=headers).status_code == 200
    assert sign_in(client, "dnegel@csumb.edu", "madeup123").status_code == 200
    assert "legend@csumb.edu: verified; is an admin" in capsys.readouterr().out


def test_unknown_email_is_reported_and_fails(db, capsys):
    assert verify_email.main(["nobody@csumb.edu"]) == 1
    assert "no account" in capsys.readouterr().out


def test_create_makes_a_verified_account_that_can_sign_in(client, db, monkeypatch):
    monkeypatch.setattr(main, "ADMIN_EMAILS", {"legend@csumb.edu"})

    assert verify_email.main(["--create", "Legend@csumb.edu"], ask=answers("brand-new-pw", "brand-new-pw")) == 0

    user = db.query(models.User).filter_by(email="legend@csumb.edu").one()
    assert user.email_verified is True
    res = sign_in(client, "legend@csumb.edu", "brand-new-pw")
    assert res.status_code == 200
    headers = {"Authorization": f"Bearer {res.json()['access_token']}"}
    assert client.get("/staff", headers=headers).status_code == 200


def test_create_refuses_odd_addresses(db):
    assert verify_email.main(["--create", "=x@csumb.edu"], ask=answers("brand-new-pw", "brand-new-pw")) == 1
    assert db.query(models.User).count() == 0


def test_password_reset_replaces_the_old_password(client, db):
    make_user(db, "legend@csumb.edu", password="forgotten1", email_verified=False)

    assert verify_email.main(["--password", "legend@csumb.edu"], ask=answers("remembered1", "remembered1")) == 0

    assert sign_in(client, "legend@csumb.edu", "forgotten1").status_code == 401
    assert sign_in(client, "legend@csumb.edu", "remembered1").status_code == 200


def test_short_or_mismatched_passwords_are_refused(db):
    make_user(db, "legend@csumb.edu", password="keepthis1")
    old_hash = db.query(models.User).filter_by(email="legend@csumb.edu").one().hashed_password

    with pytest.raises(SystemExit):
        verify_email.main(["--password", "legend@csumb.edu"], ask=answers("short", "longenough1", "different1", "x", "y"))

    db.expire_all()
    assert db.query(models.User).filter_by(email="legend@csumb.edu").one().hashed_password == old_hash


def test_google_only_accounts_have_no_password_to_reset(db):
    db.add(models.User(email="g@csumb.edu", hashed_password=main.GOOGLE_ONLY, email_verified=True))
    db.commit()
    assert verify_email.main(["--password", "g@csumb.edu"], ask=answers("whatever12", "whatever12")) == 1
