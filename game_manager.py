import uuid
from typing import Dict, Any
from fastapi import WebSocket

class GameManager:
    def __init__(self):
        # Maps a 6-digit hex room code to the live game state
        self.active_rooms: Dict[str, Dict[str, Any]] = {}

    def create_room(self, quiz_id: int, host_ws: WebSocket) -> str:
        """Generates a room and stores the TA/Professor's websocket."""
        room_code = uuid.uuid4().hex[:6].upper()
        self.active_rooms[room_code] = {
            "quiz_id": quiz_id,
            "host_ws": host_ws,
            "students": {},          # Maps player_id -> student data
            "current_state": "lobby", # States: lobby, question_active, leaderboard
            "current_question_index": 0
        }
        return room_code

    def add_student(self, room_code: str, student_name: str, websocket: WebSocket) -> str:
        """Adds a student to a room and returns their unique reconnection ID."""
        if room_code not in self.active_rooms:
            return None

        player_id = str(uuid.uuid4())
        self.active_rooms[room_code]["students"][player_id] = {
            "name": student_name,
            "ws": websocket,
            "score": 0,
            "status": "online" # We toggle this to offline if they disconnect
        }
        return player_id

    def name_taken(self, room_code: str, student_name: str) -> bool:
        """True if an online student in the room already uses this nickname (case-insensitive)."""
        room = self.active_rooms.get(room_code)
        if not room:
            return False
        wanted = student_name.strip().lower()
        return any(
            s["status"] == "online" and s["name"].strip().lower() == wanted
            for s in room["students"].values()
        )

    def reattach_student(self, room_code: str, player_id: str, websocket: WebSocket) -> bool:
        """Puts a dropped student back in the game on a new socket, keeping their score.

        Works even while the old socket still looks online: a phone that slept often
        reconnects before the server notices the old connection is dead.
        """
        room = self.active_rooms.get(room_code)
        student = room["students"].get(player_id) if room else None
        if not student:
            return False
        student["ws"] = websocket
        student["status"] = "online"
        return True

    def mark_student_offline(self, room_code: str, player_id: str):
        """Preserves the student's score if their Wi-Fi drops."""
        if room_code in self.active_rooms and player_id in self.active_rooms[room_code]["students"]:
            self.active_rooms[room_code]["students"][player_id]["status"] = "offline"

    def online_count(self, room_code: str) -> int:
        room = self.active_rooms.get(room_code)
        if not room:
            return 0
        return sum(1 for s in room["students"].values() if s["status"] == "online")

    async def broadcast_to_students(self, room_code: str, message: dict):
        """Sends a JSON payload to all online students in a room."""
        if room_code in self.active_rooms:
            for player_id, student in self.active_rooms[room_code]["students"].items():
                if student["status"] == "online":
                    try:
                        await student["ws"].send_json(message)
                    except Exception:
                        # If the send fails, assume they dropped connection
                        student["status"] = "offline"

# Initialize a single global instance of the manager
manager = GameManager()
