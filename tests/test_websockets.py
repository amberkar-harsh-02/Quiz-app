import time

import pytest
from starlette.websockets import WebSocketDisconnect

import main
import models
from conftest import make_quiz, make_user, question_data
from game_manager import manager


def token_for(user):
    return main.create_access_token({"sub": user.email, "is_professor": user.is_professor})


def recv_event(ws, event):
    """Read messages until the given event arrives (skips unrelated notifications)."""
    for _ in range(10):
        msg = ws.receive_json()
        if msg.get("event") == event:
            return msg
    raise AssertionError(f"never received {event!r}")


@pytest.fixture
def quiz(db, professor):
    return make_quiz(db, professor, "Live Quiz", questions=[
        question_data(text="Q1", correct="blue", time_limit=20),
        question_data(text="Q2", correct="red", time_limit=10, explanation=None),
    ])


def host_url(quiz, user):
    return f"/ws/host/{quiz.id}?token={token_for(user)}"


def end_game(host, *students):
    host.send_json({"event": "end_game"})
    for s in students:
        recv_event(s, "game_over")
    return recv_event(host, "game_over")


# --- host connection ---

def test_host_rejected_with_invalid_token(client, quiz):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/host/{quiz.id}?token=garbage") as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_host_rejected_when_not_professor(client, quiz, student):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(host_url(quiz, student)) as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_host_rejected_for_quiz_owned_by_someone_else(client, db, quiz):
    other = make_user(db, "other@csumb.edu", is_professor=True)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(host_url(quiz, other)) as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_host_creates_room(client, quiz, professor):
    with client.websocket_connect(host_url(quiz, professor)) as host:
        msg = host.receive_json()
        assert msg["event"] == "room_created"
        room = manager.active_rooms[msg["room_code"]]
        assert room["quiz_id"] == quiz.id
        assert room["current_state"] == "lobby"
        end_game(host)


def test_ending_in_lobby_saves_no_session(client, db, quiz, professor):
    with client.websocket_connect(host_url(quiz, professor)) as host:
        host.receive_json()
        assert end_game(host)["session_id"] is None
    assert db.query(models.GameSession).count() == 0


def test_host_disconnect_closes_room_and_tells_students(client, quiz, professor):
    host = client.websocket_connect(host_url(quiz, professor)).__enter__()
    code = host.receive_json()["room_code"]
    with client.websocket_connect(f"/ws/student/{code}?student_name=Alice") as s:
        s.receive_json()
        recv_event(host, "player_joined")

        host.__exit__(None, None, None)

        recv_event(s, "host_left")
    assert code not in manager.active_rooms


# --- student connection ---

def test_student_invalid_room_gets_error(client):
    with client.websocket_connect("/ws/student/NOPE00?student_name=Alice") as ws:
        assert ws.receive_json() == {"error": "Invalid room code or room no longer exists."}


def test_student_join_notifies_host_and_links_user(client, quiz, professor, student):
    with client.websocket_connect(host_url(quiz, professor)) as host:
        code = host.receive_json()["room_code"]

        # Room codes are accepted in any case
        with client.websocket_connect(f"/ws/student/{code.lower()}?student_name=Alice&token={token_for(student)}") as s:
            joined = s.receive_json()
            assert joined["event"] == "join_success"
            assert joined["name"] == "Alice"
            assert joined["score"] == 0
            assert host.receive_json() == {"event": "player_joined", "student_name": "Alice", "total_players": 1}
            assert manager.active_rooms[code]["students"][joined["player_id"]]["user_id"] == student.id

            end_game(host, s)


def test_student_with_bad_token_joins_as_guest(client, quiz, professor):
    with client.websocket_connect(host_url(quiz, professor)) as host:
        code = host.receive_json()["room_code"]

        with client.websocket_connect(f"/ws/student/{code}?student_name=Guest&token=bad") as s:
            pid = s.receive_json()["player_id"]
            host.receive_json()
            assert manager.active_rooms[code]["students"][pid]["user_id"] is None

            end_game(host, s)


def test_duplicate_nickname_rejected(client, quiz, professor):
    with client.websocket_connect(host_url(quiz, professor)) as host:
        code = host.receive_json()["room_code"]

        with client.websocket_connect(f"/ws/student/{code}?student_name=Alice") as first:
            first.receive_json()
            recv_event(host, "player_joined")

            with client.websocket_connect(f"/ws/student/{code}?student_name=%20alice%20") as second:
                assert second.receive_json() == {"error": "That nickname is already taken in this room."}

            end_game(host, first)


def test_blank_or_long_nickname_rejected(client, quiz, professor):
    with client.websocket_connect(host_url(quiz, professor)) as host:
        code = host.receive_json()["room_code"]
        for name in ["%20%20", "x" * 21]:
            with client.websocket_connect(f"/ws/student/{code}?student_name={name}") as s:
                assert "Nickname" in s.receive_json()["error"]
        end_game(host)


# --- full game loop ---

def test_full_game_scores_and_persists_results(client, db, quiz, professor, student):
    with client.websocket_connect(host_url(quiz, professor)) as host:
        code = host.receive_json()["room_code"]

        with client.websocket_connect(f"/ws/student/{code}?student_name=Alice&token={token_for(student)}") as alice, \
             client.websocket_connect(f"/ws/student/{code}?student_name=Bob") as bob:
            alice.receive_json()
            bob.receive_json()
            recv_event(host, "player_joined")
            recv_event(host, "player_joined")

            # Question 1: the correct answer is never sent to students
            host.send_json({"event": "start_game"})
            shown = recv_event(host, "show_question")
            assert shown["question"] == {
                "text": "Q1",
                "options": {"red": "3", "blue": "4", "yellow": "5", "green": "22"},
                "time_limit": 20,
                "index": 0,
                "total": 2,
                "image_url": None,
                "image_alt": "",
            }
            # Students get neither the correct answer nor the answer texts (those are on the projector)
            assert recv_event(alice, "show_question")["question"] == {
                "text": "Q1", "time_limit": 20, "index": 0, "total": 2, "image_url": None, "image_alt": "",
            }
            recv_event(bob, "show_question")

            # Alice answers right straight away; the forged time_remaining_ms is ignored
            alice.send_json({"event": "submit_answer", "selected_option": "blue", "time_remaining_ms": 999999})
            assert recv_event(host, "answer_received")["answers_submitted"] == 1
            bob.send_json({"event": "submit_answer", "selected_option": "green"})
            assert recv_event(host, "answer_received") == {
                "event": "answer_received", "answers_submitted": 2, "total_players": 2,
            }

            host.send_json({"event": "time_up"})
            board = recv_event(host, "leaderboard")
            alice_score = board["top_players"][0]["score"]
            assert board["top_players"][0]["name"] == "Alice"
            assert 950 <= alice_score <= 1000
            assert board["top_players"][1] == {"name": "Bob", "score": 0}
            assert board["correct_option"] == "blue"
            assert board["explanation"] == "Basic math"
            assert board["spread"] == {"red": 0, "blue": 1, "yellow": 0, "green": 1}
            assert board["is_last_question"] is False

            alice_result = recv_event(alice, "answer_result")
            assert alice_result["correct"] is True
            assert alice_result["points_earned"] == alice_score
            assert alice_result["rank"] == 1
            bob_result = recv_event(bob, "answer_result")
            assert bob_result == {
                "event": "answer_result",
                "selected_option": "green",
                "correct": False,
                "points_earned": 0,
                "correct_option": "blue",
                "correct_text": "4",
                "score": 0,
                "rank": 2,
                "total_players": 2,
            }

            # A second "close question" (e.g. auto-skip racing the timer) is ignored
            host.send_json({"event": "show_leaderboard"})

            # Question 2: only Bob answers, and correctly
            host.send_json({"event": "next_question"})
            assert recv_event(host, "show_question")["question"]["text"] == "Q2"
            recv_event(alice, "show_question")
            recv_event(bob, "show_question")
            bob.send_json({"event": "submit_answer", "selected_option": "red"})
            recv_event(host, "answer_received")

            host.send_json({"event": "show_leaderboard"})
            board = recv_event(host, "leaderboard")
            assert board["is_last_question"] is True
            assert board["explanation"] == ""
            assert recv_event(alice, "answer_result")["selected_option"] is None
            bob_score = recv_event(bob, "answer_result")["score"]
            assert 950 <= bob_score <= 1000

            # No questions left
            host.send_json({"event": "next_question"})
            recv_event(host, "quiz_finished")

            host.send_json({"event": "end_game"})
            alice_over = recv_event(alice, "game_over")
            assert alice_over["score"] == alice_score
            assert alice_over["correct_answers"] == 1
            assert alice_over["total_questions"] == 2
            assert alice_over["total_players"] == 2
            recv_event(bob, "game_over")
            session_id = recv_event(host, "game_over")["session_id"]

    assert code not in manager.active_rooms

    session = db.get(models.GameSession, session_id)
    assert session.quiz_id == quiz.id
    assert session.room_code == code
    results = {r.student_name: r for r in session.results}
    assert results["Alice"].total_score == alice_score
    assert results["Alice"].correct_answers == 1
    assert results["Alice"].user_id == student.id
    assert results["Bob"].total_score == bob_score
    assert results["Bob"].user_id is None
    bob_answers = [(a.selected_option, a.is_correct) for a in results["Bob"].answers]
    assert bob_answers == [("green", 0), ("red", 1)]


def test_answer_ignored_while_in_lobby(client, quiz, professor):
    with client.websocket_connect(host_url(quiz, professor)) as host:
        code = host.receive_json()["room_code"]
        with client.websocket_connect(f"/ws/student/{code}?student_name=Early") as s:
            pid = s.receive_json()["player_id"]
            recv_event(host, "player_joined")

            s.send_json({"event": "submit_answer", "selected_option": "blue"})

            # end_game round-trips through the student's socket, so the early answer has been handled by now
            end_game(host, s)
            assert "history" not in manager.active_rooms.get(code, {}).get("students", {}).get(pid, {})


def start_with_one_student(client, quiz, professor, name="Alice"):
    host = client.websocket_connect(host_url(quiz, professor)).__enter__()
    code = host.receive_json()["room_code"]
    s = client.websocket_connect(f"/ws/student/{code}?student_name={name}").__enter__()
    pid = s.receive_json()["player_id"]
    recv_event(host, "player_joined")
    host.send_json({"event": "start_game"})
    recv_event(host, "show_question")
    recv_event(s, "show_question")
    return host, s, code, pid


def test_invalid_color_and_late_answers_are_ignored(client, quiz, professor):
    host, s, code, pid = start_with_one_student(client, quiz, professor)
    try:
        s.send_json({"event": "submit_answer", "selected_option": "purple"})
        # Pretend the 20s question started 30s ago: past the limit plus grace
        manager.active_rooms[code]["question_started_at"] = time.monotonic() - 30
        s.send_json({"event": "submit_answer", "selected_option": "blue"})

        host.send_json({"event": "time_up"})
        result = recv_event(s, "answer_result")
        assert result["selected_option"] is None
        assert result["score"] == 0
        assert recv_event(host, "leaderboard")["spread"] == {"red": 0, "blue": 0, "yellow": 0, "green": 0}
        end_game(host, s)
    finally:
        s.__exit__(None, None, None)
        host.__exit__(None, None, None)


def test_next_question_only_advances_from_leaderboard(client, quiz, professor):
    host, s, code, pid = start_with_one_student(client, quiz, professor)
    try:
        # A stray next_question while the question is open must not skip it
        host.send_json({"event": "next_question"})
        host.send_json({"event": "time_up"})
        recv_event(host, "leaderboard")
        assert manager.active_rooms[code]["current_question_index"] == 0
        end_game(host, s)
    finally:
        s.__exit__(None, None, None)
        host.__exit__(None, None, None)


def test_student_leaving_updates_host_counts(client, quiz, professor):
    host, alice, code, _ = start_with_one_student(client, quiz, professor)
    try:
        with client.websocket_connect(f"/ws/student/{code}?student_name=Bob") as bob:
            bob.receive_json()
            assert recv_event(host, "player_joined")["total_players"] == 2
            alice.send_json({"event": "submit_answer", "selected_option": "blue"})
            recv_event(host, "answer_received")

        # Bob left without answering; Alice's answer now covers everyone still connected
        left = recv_event(host, "player_left")
        assert left["total_players"] == 1
        assert left["answers_submitted"] == 1
        assert manager.online_count(code) == 1
        end_game(host, alice)
    finally:
        alice.__exit__(None, None, None)
        host.__exit__(None, None, None)


def test_reconnect_with_player_id_keeps_score_and_resumes_question(client, quiz, professor):
    host, s, code, pid = start_with_one_student(client, quiz, professor)
    try:
        manager.active_rooms[code]["students"][pid]["score"] = 1234
        s.__exit__(None, None, None)
        assert recv_event(host, "player_left")["total_players"] == 0

        # The name in the URL is ignored on reconnect
        s = client.websocket_connect(f"/ws/student/{code}?student_name=Other&player_id={pid}").__enter__()
        joined = s.receive_json()
        assert joined == {"event": "join_success", "player_id": pid, "name": "Alice", "score": 1234}
        assert recv_event(host, "player_rejoined")["total_players"] == 1

        question = recv_event(s, "show_question")["question"]
        assert question["text"] == "Q1"
        assert 0 < question["time_remaining"] <= 20
        assert "selected_option" not in question
        assert "options" not in question

        s.send_json({"event": "submit_answer", "selected_option": "blue"})
        assert recv_event(host, "answer_received")["answers_submitted"] == 1
        assert len(manager.active_rooms[code]["students"]) == 1
        end_game(host, s)
    finally:
        s.__exit__(None, None, None)
        host.__exit__(None, None, None)


def test_reconnect_after_question_closed_gets_result(client, quiz, professor):
    host, s, code, pid = start_with_one_student(client, quiz, professor)
    try:
        s.send_json({"event": "submit_answer", "selected_option": "red"})
        recv_event(host, "answer_received")
        host.send_json({"event": "time_up"})
        recv_event(host, "leaderboard")
        recv_event(s, "answer_result")
        s.__exit__(None, None, None)
        recv_event(host, "player_left")

        s = client.websocket_connect(f"/ws/student/{code}?player_id={pid}").__enter__()
        s.receive_json()
        result = recv_event(s, "answer_result")
        assert result["selected_option"] == "red"
        assert result["correct"] is False
        end_game(host, s)
    finally:
        s.__exit__(None, None, None)
        host.__exit__(None, None, None)


# --- questions without a timer ---

def test_speed_without_timer_fades_over_a_minute():
    assert main.speed_fraction(None, 0) == 1
    assert main.speed_fraction(None, 5) == 1
    assert main.speed_fraction(None, 32.5) == 0.5
    assert main.speed_fraction(None, 300) == 0      # very late answers still count, just without a bonus
    assert main.speed_fraction(20, 0) == 1
    assert main.speed_fraction(20, 10) == 0.5
    assert main.speed_fraction(20, 30) is None      # past a timed question's deadline


@pytest.mark.parametrize("weight,speed,points", [
    (50, 1, 1000), (50, 0.5, 750), (50, 0, 500),   # the original scoring
    (0, 1, 1000), (0, 0, 1000),                    # correct answers only
    (100, 1, 1000), (100, 0.5, 500), (100, 0, 0),  # all about speed
    (30, 0.5, 850),
])
def test_points_for_correct_answer_follow_speed_weight(weight, speed, points):
    assert main.points_for_correct(speed, weight) == points


def test_untimed_question_has_no_deadline_and_waits_for_professor(client, db, professor):
    quiz = make_quiz(db, professor, "Discussion", questions=[
        question_data(text="Open", correct="blue", time_limit=None),
        question_data(text="Timed", correct="red", time_limit=20),
    ])
    host, s, code, pid = start_with_one_student(client, quiz, professor)
    try:
        room = manager.active_rooms[code]
        assert room["questions"][0]["time_limit"] is None

        # Well past any normal time limit, the answer still counts (with no speed bonus)
        room["question_started_at"] = time.monotonic() - 300
        s.send_json({"event": "submit_answer", "selected_option": "blue"})
        assert recv_event(host, "answer_received")["answers_submitted"] == 1
        # The host page closes the question once everyone has answered; here the test does it
        host.send_json({"event": "show_leaderboard"})
        result = recv_event(s, "answer_result")
        assert result["points_earned"] == 500
        assert recv_event(host, "leaderboard")["auto_advance"] is False

        host.send_json({"event": "next_question"})
        assert recv_event(s, "show_question")["question"]["time_limit"] == 20
        host.send_json({"event": "time_up"})
        assert recv_event(host, "leaderboard")["auto_advance"] is True
        end_game(host, s)
    finally:
        s.__exit__(None, None, None)
        host.__exit__(None, None, None)


def test_quiz_with_timer_off_has_no_timed_questions(client, db, professor):
    quiz = make_quiz(db, professor, "No timers", use_timer=False, questions=[question_data(time_limit=20)])
    host, s, code, pid = start_with_one_student(client, quiz, professor)
    try:
        assert manager.active_rooms[code]["questions"][0]["time_limit"] is None

        # A reconnecting student gets no countdown either
        s.__exit__(None, None, None)
        recv_event(host, "player_left")
        s = client.websocket_connect(f"/ws/student/{code}?player_id={pid}").__enter__()
        s.receive_json()
        question = recv_event(s, "show_question")["question"]
        assert question["time_limit"] is None
        assert "time_remaining" not in question
        end_game(host, s)
    finally:
        s.__exit__(None, None, None)
        host.__exit__(None, None, None)


# --- results pacing ---

def test_results_wait_for_professor_when_quiz_turns_auto_advance_off(client, db, professor):
    quiz = make_quiz(db, professor, "Paced", auto_advance_results=False, questions=[question_data(time_limit=20)])
    host, s, code, pid = start_with_one_student(client, quiz, professor)
    try:
        host.send_json({"event": "time_up"})
        assert recv_event(host, "leaderboard")["auto_advance"] is False
        end_game(host, s)
    finally:
        s.__exit__(None, None, None)
        host.__exit__(None, None, None)


def test_results_report_students_who_did_not_answer(client, quiz, professor):
    host, alice, code, _ = start_with_one_student(client, quiz, professor)
    try:
        with client.websocket_connect(f"/ws/student/{code}?student_name=Bob") as bob:
            bob.receive_json()
            recv_event(host, "player_joined")
            alice.send_json({"event": "submit_answer", "selected_option": "blue"})
            recv_event(host, "answer_received")

            host.send_json({"event": "time_up"})
            board = recv_event(host, "leaderboard")
            assert board["no_answer"] == 1
            assert board["auto_advance"] is True      # timed question, default setting
            end_game(host, alice, bob)
    finally:
        alice.__exit__(None, None, None)
        host.__exit__(None, None, None)


# --- scoring weight ---

def test_correct_only_quiz_gives_full_points_however_slow(client, db, professor):
    quiz = make_quiz(db, professor, "Correct only", speed_weight=0, questions=[question_data(time_limit=20)])
    host, s, code, pid = start_with_one_student(client, quiz, professor)
    try:
        manager.active_rooms[code]["question_started_at"] = time.monotonic() - 19.5   # just before the deadline
        s.send_json({"event": "submit_answer", "selected_option": "blue"})
        recv_event(host, "answer_received")
        host.send_json({"event": "time_up"})
        assert recv_event(s, "answer_result")["points_earned"] == 1000
        end_game(host, s)
    finally:
        s.__exit__(None, None, None)
        host.__exit__(None, None, None)


def test_room_created_reports_scoring_weight(client, db, professor):
    quiz = make_quiz(db, professor, "Speedy", speed_weight=70, questions=[question_data()])
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        created = host.receive_json()
        assert created["speed_weight"] == 70
        end_game(host)


# --- question images ---

def test_question_image_reaches_host_and_students(client, db, professor):
    db.add(models.Image(id="a" * 32, owner_id=professor.id, content_type="image/png", data=b"x"))
    q = question_data(text="Look at the diagram")
    q.update(image_id="a" * 32, image_alt="Network diagram")
    quiz = make_quiz(db, professor, "Pictures", questions=[q])
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        code = host.receive_json()["room_code"]
        with client.websocket_connect(f"/ws/student/{code}?student_name=Alice") as s:
            s.receive_json()
            recv_event(host, "player_joined")
            host.send_json({"event": "start_game"})
            for ws in (host, s):
                question = recv_event(ws, "show_question")["question"]
                assert question["image_url"] == "/images/" + "a" * 32
                assert question["image_alt"] == "Network diagram"
            end_game(host, s)
