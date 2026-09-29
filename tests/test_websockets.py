import pytest
from starlette.websockets import WebSocketDisconnect

import main
import models
from conftest import make_quiz, question_data
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
        question_data(text="Q2", correct="red", time_limit=10),
    ])


# --- host connection ---

def test_host_rejected_with_invalid_token(client, quiz):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/host/{quiz.id}?token=garbage") as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_host_rejected_when_not_professor(client, quiz, student):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(student)}") as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_host_creates_room(client, quiz, professor):
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        msg = host.receive_json()
        assert msg["event"] == "room_created"
        room = manager.active_rooms[msg["room_code"]]
        assert room["quiz_id"] == quiz.id
        assert room["current_state"] == "lobby"
        host.send_json({"event": "end_game"})
        recv_event(host, "game_over")


def test_host_disconnect_mid_lobby_does_not_crash(client, quiz, professor):
    # Regression: the host's disconnect handler used to reference an undefined player_id
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        code = host.receive_json()["room_code"]
    assert code in manager.active_rooms


# --- student connection ---

def test_student_invalid_room_gets_error(client):
    with client.websocket_connect("/ws/student/NOPE00?student_name=Alice") as ws:
        assert ws.receive_json() == {"error": "Invalid room code or room no longer exists."}


def test_student_join_notifies_host_and_links_user(client, quiz, professor, student):
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        code = host.receive_json()["room_code"]

        with client.websocket_connect(f"/ws/student/{code}?student_name=Alice&token={token_for(student)}") as s:
            joined = s.receive_json()
            assert joined["event"] == "join_success"
            assert host.receive_json() == {"event": "player_joined", "student_name": "Alice", "total_players": 1}
            assert manager.active_rooms[code]["students"][joined["player_id"]]["user_id"] == student.id

            host.send_json({"event": "end_game"})
            recv_event(s, "game_over")
            recv_event(host, "game_over")


def test_student_with_bad_token_joins_as_guest(client, quiz, professor):
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        code = host.receive_json()["room_code"]

        with client.websocket_connect(f"/ws/student/{code}?student_name=Guest&token=bad") as s:
            pid = s.receive_json()["player_id"]
            host.receive_json()
            assert manager.active_rooms[code]["students"][pid]["user_id"] is None

            host.send_json({"event": "end_game"})
            recv_event(s, "game_over")
            recv_event(host, "game_over")


# --- full game loop ---

def test_full_game_scores_and_persists_results(client, db, quiz, professor, student):
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        code = host.receive_json()["room_code"]

        with client.websocket_connect(f"/ws/student/{code}?student_name=Alice&token={token_for(student)}") as alice, \
             client.websocket_connect(f"/ws/student/{code}?student_name=Bob") as bob:
            alice_id = alice.receive_json()["player_id"]
            bob_id = bob.receive_json()["player_id"]
            recv_event(host, "player_joined")
            recv_event(host, "player_joined")

            # Question 1: correct answer hides from students
            host.send_json({"event": "start_game"})
            shown = recv_event(host, "show_question")
            assert shown["question"] == {
                "text": "Q1",
                "options": {"red": "3", "blue": "4", "yellow": "5", "green": "22"},
                "time_limit": 20,
            }
            assert "correct" not in recv_event(alice, "show_question")["question"]
            recv_event(bob, "show_question")

            # Alice answers correctly with half the time left: 500 + 250 speed bonus
            alice.send_json({"event": "submit_answer", "selected_option": "blue", "time_remaining_ms": 10000})
            assert recv_event(host, "answer_received")["answers_submitted"] == 1
            # Bob answers wrong: no points
            bob.send_json({"event": "submit_answer", "selected_option": "green", "time_remaining_ms": 19000})
            assert recv_event(host, "answer_received") == {
                "event": "answer_received", "answers_submitted": 2, "total_players": 2,
            }

            host.send_json({"event": "time_up"})
            board = recv_event(host, "leaderboard")
            assert board["top_players"] == [{"name": "Alice", "score": 750}, {"name": "Bob", "score": 0}]
            assert recv_event(alice, "leaderboard")["scores"] == {alice_id: 750, bob_id: 0}
            recv_event(bob, "leaderboard")

            # Question 2: Bob answers correctly with no time info -> flat 500
            host.send_json({"event": "next_question"})
            assert recv_event(host, "show_question")["question"]["text"] == "Q2"
            recv_event(alice, "show_question")
            recv_event(bob, "show_question")
            bob.send_json({"event": "submit_answer", "selected_option": "red"})
            recv_event(host, "answer_received")

            host.send_json({"event": "show_leaderboard"})
            assert recv_event(host, "leaderboard")["top_players"][1] == {"name": "Bob", "score": 500}
            recv_event(alice, "leaderboard")
            recv_event(bob, "leaderboard")

            # No questions left
            host.send_json({"event": "next_question"})
            recv_event(host, "quiz_finished")

            host.send_json({"event": "end_game"})
            over = recv_event(alice, "game_over")
            assert over["scores"] == {alice_id: 750, bob_id: 500}
            recv_event(bob, "game_over")
            session_id = recv_event(host, "game_over")["session_id"]

    assert code not in manager.active_rooms

    session = db.get(models.GameSession, session_id)
    assert session.quiz_id == quiz.id
    assert session.room_code == code
    results = {r.student_name: r for r in session.results}
    assert results["Alice"].total_score == 750
    assert results["Alice"].correct_answers == 1
    assert results["Alice"].user_id == student.id
    assert results["Bob"].total_score == 500
    assert results["Bob"].user_id is None
    bob_answers = [(a.selected_option, a.is_correct) for a in results["Bob"].answers]
    assert bob_answers == [("green", 0), ("red", 1)]


def test_answer_ignored_while_in_lobby(client, quiz, professor):
    with client.websocket_connect(f"/ws/host/{quiz.id}?token={token_for(professor)}") as host:
        code = host.receive_json()["room_code"]
        with client.websocket_connect(f"/ws/student/{code}?student_name=Early") as s:
            pid = s.receive_json()["player_id"]
            recv_event(host, "player_joined")

            s.send_json({"event": "submit_answer", "selected_option": "blue", "time_remaining_ms": 1000})

            # end_game round-trips through the student's socket, so the early answer has been handled by now
            host.send_json({"event": "end_game"})
            assert recv_event(s, "game_over")["scores"] == {pid: 0}
            recv_event(host, "game_over")
