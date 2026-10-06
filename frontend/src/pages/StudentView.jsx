import { useState, useRef, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { WS_URL, apiFetch, clearToken, getToken, readToken, setToken } from '../api';
import JoinScreen from '../components/student/JoinScreen';
import StudentDashboard from '../components/student/StudentDashboard';
import GameScreen from '../components/student/GameScreen';

// Per tab, so a refresh rejoins the same game while other tabs can play as other students
const GAME_KEY = 'kahoot_game';
const MAX_RECONNECT_ATTEMPTS = 5;

function loadSavedGame() {
  try {
    return JSON.parse(sessionStorage.getItem(GAME_KEY));
  } catch {
    return null;
  }
}

export default function StudentView() {
  const [user, setUser] = useState(readToken);
  const [history, setHistory] = useState([]);
  const [historyError, setHistoryError] = useState('');
  const [reviewSessionId, setReviewSessionId] = useState(null);
  const [joinError, setJoinError] = useState('');

  // null while on the menu; otherwise the live game shown by GameScreen
  const [game, setGame] = useState(() => {
    const saved = loadSavedGame();
    return saved ? { phase: 'waiting', roomCode: saved.roomCode, name: '', score: 0, reconnecting: true } : null;
  });

  const ws = useRef(null);
  const retry = useRef({ attempts: 0, timer: null });
  const navigate = useNavigate();

  const isStudent = user && !user.is_professor;

  const loadHistory = useCallback(() => {
    apiFetch('/student/history')
      .then((data) => { setHistory(data); setHistoryError(''); })
      .catch((err) => setHistoryError(err.message));
  }, []);

  useEffect(() => {
    if (isStudent) loadHistory();
  }, [isStudent, loadHistory]);

  const connect = useCallback(function connectTo(roomCode, { name, playerId } = {}) {
    const params = new URLSearchParams();
    if (name) params.set('student_name', name);
    if (playerId) params.set('player_id', playerId);
    const token = getToken();
    if (token) params.set('token', token);

    const socket = new WebSocket(`${WS_URL}/ws/student/${roomCode}?${params}`);
    ws.current = socket;
    // Set when the game is over for this student, so the close that follows isn't treated as a drop
    let finished = false;

    const endGame = (update) => {
      finished = true;
      sessionStorage.removeItem(GAME_KEY);
      setGame((g) => ({ ...g, ...update, reconnecting: false }));
    };

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.error) {
        finished = true;
        sessionStorage.removeItem(GAME_KEY);
        setGame(null);
        setJoinError(playerId ? 'That game has already ended.' : data.error);
        return;
      }

      if (data.event === 'join_success') {
        retry.current.attempts = 0;
        sessionStorage.setItem(GAME_KEY, JSON.stringify({ roomCode, playerId: data.player_id }));
        setGame((g) => ({
          phase: 'waiting',
          ...g,
          roomCode,
          name: data.name,
          score: data.score,
          reconnecting: false,
        }));
      } else if (data.event === 'show_question') {
        const q = data.question;
        const secondsLeft = q.time_remaining ?? q.time_limit;   // both null when there's no timer
        setGame((g) => ({
          ...g,
          phase: q.selected_option ? 'answered' : 'question',
          question: q,
          selected: q.selected_option ?? null,
          deadline: secondsLeft == null ? null : Date.now() + secondsLeft * 1000,
          result: null,
        }));
      } else if (data.event === 'answer_result') {
        setGame((g) => ({ ...g, phase: 'result', result: data, score: data.score }));
      } else if (data.event === 'game_over') {
        endGame({ phase: 'game_over', final: data, score: data.score });
      } else if (data.event === 'host_left') {
        endGame({ phase: 'host_left' });
      }
    };

    socket.onclose = () => {
      // Ignore sockets we closed ourselves or that a newer connection replaced
      if (finished || ws.current !== socket) return;

      const saved = loadSavedGame();
      if (!saved) {
        setGame(null);
        setJoinError('Could not reach the game server.');
        return;
      }
      if (retry.current.attempts >= MAX_RECONNECT_ATTEMPTS) {
        sessionStorage.removeItem(GAME_KEY);
        setGame(null);
        setJoinError('Lost connection to the game.');
        return;
      }

      const delay = 1000 * 2 ** retry.current.attempts;
      retry.current.attempts += 1;
      setGame((g) => ({ ...g, reconnecting: true }));
      retry.current.timer = setTimeout(() => connectTo(saved.roomCode, { playerId: saved.playerId }), delay);
    };
  }, []);

  // Rejoin after a refresh, and close the socket when leaving the page
  useEffect(() => {
    const saved = loadSavedGame();
    if (saved) connect(saved.roomCode, { playerId: saved.playerId });

    const retryState = retry.current;
    return () => {
      clearTimeout(retryState.timer);
      const socket = ws.current;
      ws.current = null;
      socket?.close();
    };
  }, [connect]);

  const joinGame = (roomCode, name) => {
    setJoinError('');
    retry.current.attempts = 0;
    setGame({ phase: 'waiting', roomCode, name, score: 0, reconnecting: false });
    connect(roomCode, { name });
  };

  const exitGame = () => {
    clearTimeout(retry.current.timer);
    const socket = ws.current;
    ws.current = null;
    socket?.close();
    sessionStorage.removeItem(GAME_KEY);
    setGame(null);
    if (isStudent) loadHistory();
  };

  const reviewGame = (sessionId) => {
    exitGame();
    setReviewSessionId(sessionId);
  };

  const signIn = (token) => {
    setToken(token);
    const payload = readToken();
    if (payload?.is_professor) {
      navigate('/host');
      return;
    }
    setUser(payload);
  };

  const signOut = () => {
    clearToken();
    setUser(null);
    setHistory([]);
  };

  if (game) {
    return (
      <GameScreen
        game={game}
        isSignedIn={Boolean(isStudent)}
        onAnswer={(color) => {
          if (game.phase !== 'question') return;
          ws.current?.send(JSON.stringify({ event: 'submit_answer', selected_option: color }));
          setGame((g) => ({ ...g, phase: 'answered', selected: color }));
        }}
        onExit={exitGame}
        onReview={reviewGame}
      />
    );
  }

  if (isStudent) {
    return (
      <StudentDashboard
        email={user.sub}
        history={history}
        historyError={historyError}
        joinError={joinError}
        onJoin={joinGame}
        onSignOut={signOut}
        expandedId={reviewSessionId}
        onToggle={(id) => setReviewSessionId(reviewSessionId === id ? null : id)}
      />
    );
  }

  return (
    <JoinScreen
      professorEmail={user?.is_professor ? user.sub : null}
      joinError={joinError}
      onJoin={joinGame}
      onSignIn={signIn}
      onSignOut={signOut}
    />
  );
}
