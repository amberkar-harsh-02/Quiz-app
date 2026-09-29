import asyncio
from unittest.mock import AsyncMock, MagicMock

from game_manager import GameManager


def test_create_room_returns_six_char_uppercase_code():
    gm = GameManager()
    code = gm.create_room(quiz_id=7, host_ws=MagicMock())

    assert len(code) == 6
    assert code == code.upper()
    assert code in gm.active_rooms


def test_create_room_initial_state():
    gm = GameManager()
    host = MagicMock()
    code = gm.create_room(quiz_id=7, host_ws=host)
    room = gm.active_rooms[code]

    assert room["quiz_id"] == 7
    assert room["host_ws"] is host
    assert room["students"] == {}
    assert room["current_state"] == "lobby"
    assert room["current_question_index"] == 0


def test_create_room_generates_unique_codes():
    gm = GameManager()
    codes = {gm.create_room(1, MagicMock()) for _ in range(50)}
    assert len(codes) == 50


def test_add_student_to_existing_room():
    gm = GameManager()
    code = gm.create_room(1, MagicMock())
    ws = MagicMock()

    player_id = gm.add_student(code, "Alice", ws)

    student = gm.active_rooms[code]["students"][player_id]
    assert student == {"name": "Alice", "ws": ws, "score": 0, "status": "online"}


def test_add_student_gives_each_player_a_unique_id():
    gm = GameManager()
    code = gm.create_room(1, MagicMock())

    p1 = gm.add_student(code, "Alice", MagicMock())
    p2 = gm.add_student(code, "Alice", MagicMock())

    assert p1 != p2
    assert len(gm.active_rooms[code]["students"]) == 2


def test_add_student_to_missing_room_returns_none():
    gm = GameManager()
    assert gm.add_student("NOPE00", "Alice", MagicMock()) is None


def test_mark_student_offline_preserves_score():
    gm = GameManager()
    code = gm.create_room(1, MagicMock())
    pid = gm.add_student(code, "Alice", MagicMock())
    gm.active_rooms[code]["students"][pid]["score"] = 1200

    gm.mark_student_offline(code, pid)

    student = gm.active_rooms[code]["students"][pid]
    assert student["status"] == "offline"
    assert student["score"] == 1200


def test_mark_student_offline_ignores_unknown_room_or_player():
    gm = GameManager()
    code = gm.create_room(1, MagicMock())
    # Neither call should raise
    gm.mark_student_offline("NOPE00", "whoever")
    gm.mark_student_offline(code, "unknown-player")


def test_broadcast_sends_only_to_online_students():
    gm = GameManager()
    code = gm.create_room(1, MagicMock())
    online_ws, offline_ws = AsyncMock(), AsyncMock()
    gm.add_student(code, "Online", online_ws)
    offline_id = gm.add_student(code, "Offline", offline_ws)
    gm.mark_student_offline(code, offline_id)

    message = {"event": "ping"}
    asyncio.run(gm.broadcast_to_students(code, message))

    online_ws.send_json.assert_awaited_once_with(message)
    offline_ws.send_json.assert_not_awaited()


def test_broadcast_marks_student_offline_when_send_fails():
    gm = GameManager()
    code = gm.create_room(1, MagicMock())
    broken_ws, healthy_ws = AsyncMock(), AsyncMock()
    broken_ws.send_json.side_effect = RuntimeError("connection lost")
    broken_id = gm.add_student(code, "Broken", broken_ws)
    healthy_id = gm.add_student(code, "Healthy", healthy_ws)

    asyncio.run(gm.broadcast_to_students(code, {"event": "ping"}))

    students = gm.active_rooms[code]["students"]
    assert students[broken_id]["status"] == "offline"
    assert students[healthy_id]["status"] == "online"
    healthy_ws.send_json.assert_awaited_once()


def test_broadcast_to_missing_room_is_noop():
    gm = GameManager()
    asyncio.run(gm.broadcast_to_students("NOPE00", {"event": "ping"}))
