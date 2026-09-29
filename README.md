# CST 315 Real-Time Quiz App

A Kahoot-style live quiz for CST 315 (Introduction to Cybersecurity). The backend is FastAPI with WebSockets and SQLite; the frontend is React + Vite + Tailwind.

- **Host** (professor/TA): builds or uploads quizzes, runs a live game on the projector, reviews per-session analytics.
- **Students**: join from a phone or laptop with a room PIN, as a guest or signed in with a `@csumb.edu` account. Signed-in students can review past quizzes with explanations.

## Setup

### Backend

```bash
python -m venv venv
venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --reload
```

`--host 0.0.0.0` lets phones on the same Wi-Fi reach the API. Use plain `uvicorn main:app --reload` if only this machine needs it.

Create a `.env` file next to `main.py`:

| Variable | Required | Purpose |
| --- | --- | --- |
| `SECRET_KEY` | yes | Signs login tokens. Use a long random string: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `GOOGLE_CLIENT_ID` | for Google sign-in | OAuth client ID from Google Cloud Console |
| `PROFESSOR_EMAILS` | yes, to host | Comma-separated emails that get host rights, e.g. `prof@csumb.edu,ta@csumb.edu`. Everyone else is a student. |
| `FRONTEND_ORIGIN` | no | Comma-separated origins allowed by CORS. Leave unset in dev to allow any origin on port 5173. |

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Optional `frontend/.env.local`:

- `VITE_GOOGLE_CLIENT_ID` – same value as `GOOGLE_CLIENT_ID`.
- `VITE_API_URL` – backend URL. Defaults to the page's own host on port 8000, which is what you want on a LAN.

### Joining from phones

1. Put the laptop and phones on the same network.
2. Find the laptop's LAN IP (`ipconfig` on Windows, `ipconfig getifaddr en0` on macOS).
3. Open `http://<LAN-IP>:5173` on the laptop and host a game. The lobby shows the join link with the PIN already filled in.

Campus Wi-Fi may block device-to-device traffic. If phones can't connect, use a phone hotspot or deploy the app.

## Quiz JSON format

Upload from the host dashboard with **Upload JSON**:

```json
{
  "title": "Week 3 – Cryptography",
  "questions": [
    {
      "text": "Which of these is a symmetric cipher?",
      "option_red": "RSA",
      "option_blue": "AES",
      "option_yellow": "ECDSA",
      "option_green": "Diffie-Hellman",
      "correct_option": "blue",
      "time_limit_seconds": 20,
      "explanation": "AES uses the same key to encrypt and decrypt."
    }
  ]
}
```

- `correct_option` is one of `red`, `blue`, `yellow`, `green`.
- `time_limit_seconds` is optional (default 15, allowed 5–120).
- `explanation` is optional. Students see it on their review page.

## Scoring

A correct answer is worth 500 points plus up to 500 for speed. The server measures the time; the client can't change it. Wrong or missing answers score 0.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests use an in-memory database and never touch `kahoot.db`.

## Database

SQLite file `kahoot.db`, created on first start. New columns are added automatically at startup, so existing data is kept.

Quizzes that have been played can't be edited or deleted, because their sessions hold student grades. Use **Duplicate** to make a changed copy.

To start over, stop the server and delete `kahoot.db` (plus `kahoot.db-wal` / `kahoot.db-shm`).
