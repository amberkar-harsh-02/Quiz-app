"""Limits that keep one person from hurting other people's games, accounts or exports."""
import asyncio
import csv
import io
import uuid

import pytest
from starlette.websockets import WebSocketDisconnect

import game_manager
import images
import main
import models
from conftest import auth_header, make_quiz, make_session, make_user, question_data
from game_manager import manager
from test_images import picture, upload
from test_websockets import host_url, quiz, recv_event  # noqa: F401  (quiz is a fixture)


# --- rooms ---

def test_room_stops_accepting_players_when_full(client, quiz, professor, monkeypatch):
    monkeypatch.setattr(game_manager, "MAX_PLAYERS_PER_ROOM", 2)
    with client.websocket_connect(host_url(quiz, professor)) as host:
        code = host.receive_json()["room_code"]
        # Players who drop still count: their place is kept so they can rejoin
        for name in ("A", "B"):
            with client.websocket_connect(f"/ws/student/{code}?student_name={name}") as s:
                recv_event(s, "join_success")
        with client.websocket_connect(f"/ws/student/{code}?student_name=C") as late:
            assert "full" in late.receive_json()["error"]
        assert len(manager.active_rooms[code]["students"]) == 2


def test_room_codes_never_collide_with_a_live_room(monkeypatch):
    same = uuid.UUID("abcdef00000000000000000000000000")
    fresh = uuid.UUID("12345600000000000000000000000000")
    picks = iter([same, same, fresh])
    monkeypatch.setattr(game_manager.uuid, "uuid4", lambda: next(picks))

    first = manager.create_room(1, object())
    second = manager.create_room(2, object())

    assert first == "ABCDEF" and second == "123456"
    assert manager.active_rooms[first]["quiz_id"] == 1


def test_broadcast_survives_a_join_while_a_send_is_waiting():
    code = manager.create_room(1, object())

    class SlowSocket:
        async def send_json(self, message):
            await asyncio.sleep(0)
            manager.add_student(code, "late", SlowSocket())  # someone joins mid-broadcast

    manager.add_student(code, "early", SlowSocket())
    asyncio.run(manager.broadcast_to_students(code, {"event": "x"}))  # used to raise RuntimeError

    assert len(manager.active_rooms[code]["students"]) >= 2


def test_oversized_student_message_closes_only_that_socket(client, quiz, professor):
    with client.websocket_connect(host_url(quiz, professor)) as host:
        code = host.receive_json()["room_code"]
        with client.websocket_connect(f"/ws/student/{code}?student_name=Big") as big, \
             client.websocket_connect(f"/ws/student/{code}?student_name=Ok") as ok:
            recv_event(big, "join_success")
            recv_event(ok, "join_success")
            big.send_text('{"x": "' + "a" * 5000 + '"}')
            with pytest.raises(WebSocketDisconnect) as closed:
                big.receive_json()
            assert closed.value.code == 1009

            # Junk that isn't an object is ignored; the other student plays on
            ok.send_text("[1, 2, 3]")
            ok.send_text("not json")
            host.send_json({"event": "start_game"})
            recv_event(ok, "show_question")
            ok.send_json({"event": "submit_answer", "selected_option": "blue"})
            assert recv_event(host, "answer_received")["answers_submitted"] == 1


# --- images ---

def test_huge_image_is_refused_before_it_is_decoded(client, professor, monkeypatch):
    data = picture("PNG", size=(20, 20))
    monkeypatch.setattr(images, "MAX_PIXELS", 100)
    decoded = []
    monkeypatch.setattr(images.Image.Image, "load", lambda self: decoded.append(1))

    res = upload(client, professor, data)

    assert res.status_code == 400
    assert "too large" in res.json()["detail"]
    assert decoded == []


# --- sign-in ---

def test_wrong_passwords_lock_that_account_for_a_while(client, professor):
    for _ in range(10):
        assert client.post("/token", data={"username": "prof@csumb.edu", "password": "wrong"}).status_code == 401
    # Even the right password waits now
    res = client.post("/token", data={"username": "prof@csumb.edu", "password": "password123"})
    assert res.status_code == 429


def test_sign_in_attempts_are_limited_per_client(client, monkeypatch):
    monkeypatch.setattr(main.sign_in_attempts, "limit", 3)
    codes = [client.post("/token", data={"username": f"u{i}@csumb.edu", "password": "x"}).status_code for i in range(4)]
    assert codes == [401, 401, 401, 429]
    assert client.post("/register", json={"email": "new@csumb.edu", "password": "longenough1"}).status_code == 429


def test_google_certificates_are_fetched_once_and_reused():
    calls = []

    class Response:
        status = 200
        data = b"{}"

    request = main.CachedCertsRequest()
    request.inner = lambda url, method="GET", **kw: calls.append(url) or Response()

    for _ in range(3):
        request("https://www.googleapis.com/oauth2/v1/certs")

    assert len(calls) == 1


@pytest.mark.parametrize("email", ["=1+1@csumb.edu", "+cmd@csumb.edu", "a b@csumb.edu", "@csumb.edu"])
def test_sign_up_rejects_odd_email_addresses(client, email):
    assert client.post("/register", json={"email": email, "password": "longenough1"}).status_code == 400


# --- staff list ---

def test_staff_removal_is_not_undone_by_a_restart(client, db, admin, professor):
    main.seed_staff_emails()  # first start: carries existing access over
    client.delete("/staff/prof@csumb.edu", headers=auth_header(admin))

    main.seed_staff_emails()  # a later restart

    assert db.query(models.StaffEmail).filter_by(email="prof@csumb.edu").count() == 0
    assert client.get("/quizzes/", headers=auth_header(professor)).status_code == 403


def test_former_admin_loses_hosting_as_soon_as_removed_from_settings(client, db, monkeypatch):
    old_admin = make_user(db, "old@csumb.edu")
    old_admin.is_professor = True  # flag left over from when they were an admin
    db.commit()
    monkeypatch.setattr(main, "ADMIN_EMAILS", set())

    assert client.get("/quizzes/", headers=auth_header(old_admin)).status_code == 403


# --- gradebook export ---

def test_every_text_column_in_grades_csv_is_formula_safe(client, db, professor):
    quiz = make_quiz(db, professor, questions=[question_data()])
    session = make_session(db, quiz)
    # An address saved before sign-up checked the format
    legacy = models.User(email="=HYPERLINK(1)@csumb.edu", hashed_password="x")
    db.add(legacy)
    db.commit()
    db.add(models.StudentResult(session_id=session.id, student_name="-2", total_score=0, correct_answers=0, user_id=legacy.id))
    db.commit()

    rows = list(csv.reader(io.StringIO(client.get(f"/analytics/{session.id}/grades.csv", headers=auth_header(professor)).text)))

    assert rows[1][:2] == ["'-2", "'=HYPERLINK(1)@csumb.edu"]
