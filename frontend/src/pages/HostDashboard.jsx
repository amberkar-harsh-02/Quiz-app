import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { WS_URL, apiFetch, clearToken, getToken, readToken } from '../api';
import { Alert, Button, Panel, Wordmark } from '../components/ui';
import Stage from '../components/host/Stage';
import Lobby from '../components/host/Lobby';
import QuestionStage from '../components/host/QuestionStage';
import RevealStage from '../components/host/RevealStage';
import GameOverStage from '../components/host/GameOverStage';

export default function HostDashboard() {
  const [quizzes, setQuizzes] = useState([]);
  const [view, setView] = useState('dashboard'); // dashboard, lobby, question, leaderboard, game_over
  const [roomCode, setRoomCode] = useState('');
  const [players, setPlayers] = useState([]);
  const [totalPlayers, setTotalPlayers] = useState(0);
  const [message, setMessage] = useState(null); // { type: 'error' | 'success', text }
  const [isAdmin, setIsAdmin] = useState(false);
  const [speedWeight, setSpeedWeight] = useState(50);

  // Game States
  const [currentQuestion, setCurrentQuestion] = useState(null);
  const [timeLeft, setTimeLeft] = useState(0);
  const [answersCount, setAnswersCount] = useState(0);
  const [leaderboard, setLeaderboard] = useState([]);
  const [reveal, setReveal] = useState(null); // correct answer, spread and explanation for the question just closed
  const [savedSessionId, setSavedSessionId] = useState(null);

  // Leaderboard auto-advance timer
  const [leaderboardTimeLeft, setLeaderboardTimeLeft] = useState(5);

  const ws = useRef(null);
  const fileInputRef = useRef(null);
  const navigate = useNavigate();

  const loadQuizzes = () => apiFetch('/quizzes/').then(setQuizzes);

  // Load Professor's Quizzes
  useEffect(() => {
    if (!readToken()) { navigate('/'); return; }
    // Someone removed from the staff list goes back to the student side
    apiFetch('/me')
      .then((me) => (me.is_professor ? setIsAdmin(me.is_admin) : navigate('/')))
      .catch(() => {});
    apiFetch('/quizzes/')
      .then(setQuizzes)
      .catch((err) => setMessage({ type: 'error', text: `Couldn't load your quizzes: ${err.message}` }));
  }, [navigate]);

  // Close the game socket when leaving the page
  useEffect(() => () => ws.current?.close(), []);

  // Question Timer Logic
  useEffect(() => {
    if (view === 'question' && timeLeft > 0) {
      const timerId = setTimeout(() => setTimeLeft(timeLeft - 1), 1000);
      return () => clearTimeout(timerId);
    } else if (view === 'question' && timeLeft === 0) {
      ws.current.send(JSON.stringify({ event: 'time_up' }));
    }
  }, [timeLeft, view]);

  // Fast-Paced Auto-Skip Logic (If everyone answers). The server ignores a repeat close.
  useEffect(() => {
    if (view === 'question' && totalPlayers > 0 && answersCount >= totalPlayers) {
      ws.current.send(JSON.stringify({ event: 'show_leaderboard' }));
    }
  }, [answersCount, totalPlayers, view]);

  // Leaderboard Auto-Advance Logic
  useEffect(() => {
    if (view === 'leaderboard' && leaderboardTimeLeft > 0) {
      const timerId = setTimeout(() => setLeaderboardTimeLeft(leaderboardTimeLeft - 1), 1000);
      return () => clearTimeout(timerId);
    } else if (view === 'leaderboard' && leaderboardTimeLeft === 0) {
      ws.current.send(JSON.stringify({ event: 'next_question' }));
    }
  }, [leaderboardTimeLeft, view]);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    e.target.value = null;
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      const quiz = await apiFetch('/quizzes/upload/', { method: 'POST', body: formData });
      await loadQuizzes();
      setMessage({ type: 'success', text: `Uploaded "${quiz.title}" with ${quiz.questions.length} questions.` });
    } catch (err) {
      setMessage({ type: 'error', text: `Upload failed: ${err.message}` });
    }
  };

  const deleteQuiz = async (quiz) => {
    if (!window.confirm(`Delete "${quiz.title}"? This cannot be undone.`)) return;
    try {
      await apiFetch(`/quizzes/${quiz.id}`, { method: 'DELETE' });
      setQuizzes(quizzes.filter(q => q.id !== quiz.id));
      setMessage(null);
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    }
  };

  const hostGame = (quizId) => {
    ws.current?.close();
    setMessage(null);
    setPlayers([]);
    setTotalPlayers(0);
    setAnswersCount(0);
    setLeaderboard([]);
    setReveal(null);
    setRoomCode('');
    setCurrentQuestion(null);

    const socket = new WebSocket(`${WS_URL}/ws/host/${quizId}?token=${getToken()}`);
    ws.current = socket;
    let started = false;
    let finished = false;

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data);

      if (data.event === 'room_created') {
        started = true;
        setRoomCode(data.room_code);
        setSpeedWeight(data.speed_weight ?? 50);
        setView('lobby');
      } else if (data.event === 'player_joined') {
        setPlayers(prev => [...prev, data.student_name]);
        setTotalPlayers(data.total_players);
      } else if (data.event === 'player_left' || data.event === 'player_rejoined') {
        setTotalPlayers(data.total_players);
        setAnswersCount(data.answers_submitted);
      } else if (data.event === 'show_question') {
        setCurrentQuestion(data.question);
        // null for a question without a timer, which stops the countdown effect above
        setTimeLeft(data.question.time_limit);
        setAnswersCount(0);
        setView('question');
      } else if (data.event === 'answer_received') {
        setAnswersCount(data.answers_submitted);
        setTotalPlayers(data.total_players);
      } else if (data.event === 'leaderboard') {
        setLeaderboard(data.top_players);
        setReveal(data);
        // Leave time to read the explanation out
        // After an untimed question the results wait for the professor (null stops the countdown)
        setLeaderboardTimeLeft(data.auto_advance === false ? null : data.explanation ? 10 : 5);
        setView('leaderboard');
      } else if (data.event === 'quiz_finished') {
        // Automatically end the game when out of questions
        socket.send(JSON.stringify({ event: 'end_game' }));
      } else if (data.event === 'game_over') {
        finished = true;
        setSavedSessionId(data.session_id);
        setView('game_over');
      }
    };

    socket.onclose = () => {
      if (finished || ws.current !== socket) return;
      setView('dashboard');
      setMessage({
        type: 'error',
        text: started
          ? 'Lost connection to the game server. The game has ended.'
          : "Couldn't start the game. Check that the server is running and you're signed in as this quiz's owner.",
      });
    };
  };

  const startGame = () => ws.current.send(JSON.stringify({ event: 'start_game' }));
  const nextQuestion = () => ws.current.send(JSON.stringify({ event: 'next_question' }));
  const showLeaderboard = () => ws.current.send(JSON.stringify({ event: 'show_leaderboard' }));
  const endGame = () => ws.current.send(JSON.stringify({ event: 'end_game' }));

  if (view !== 'dashboard') {
    return (
      <Stage roomCode={view === 'game_over' ? null : roomCode} playerCount={totalPlayers}>
        {view === 'lobby' && <Lobby roomCode={roomCode} players={players} totalPlayers={totalPlayers} speedWeight={speedWeight} onStart={startGame} />}

        {view === 'question' && currentQuestion && (
          <QuestionStage question={currentQuestion} timeLeft={timeLeft} answersCount={answersCount} totalPlayers={totalPlayers} onSkip={showLeaderboard} />
        )}

        {view === 'leaderboard' && reveal && currentQuestion && (
          <RevealStage
            question={currentQuestion}
            reveal={reveal}
            leaderboard={leaderboard}
            secondsLeft={leaderboardTimeLeft}
            onNext={nextQuestion}
            onEnd={endGame}
          />
        )}

        {view === 'game_over' && (
          <GameOverStage
            saved={Boolean(savedSessionId)}
            onDashboard={() => {
              ws.current?.close();
              loadQuizzes().catch(() => {});
              setView('dashboard');
            }}
            onAnalytics={() => navigate('/analytics')}
          />
        )}
      </Stage>
    );
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-6 py-3">
          <Wordmark title="Quiz App" />
          <nav className="flex items-center gap-2">
            {isAdmin && <Button variant="ghost" size="sm" onClick={() => navigate('/staff')}>Staff</Button>}
            <Button variant="ghost" size="sm" onClick={() => navigate('/analytics')}>View Analytics</Button>
            <Button variant="ghost" size="sm" onClick={() => { clearToken(); navigate('/'); }}>Log Out</Button>
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
          <h1 className="text-3xl font-bold tracking-tight">My Quizzes</h1>
          <div className="flex gap-3">
            <input type="file" accept=".json" ref={fileInputRef} onChange={handleFileUpload} className="hidden" />
            <Button variant="secondary" onClick={() => fileInputRef.current.click()}>Upload JSON</Button>
            <Button onClick={() => navigate('/create')}>+ Create Quiz</Button>
          </div>
        </div>

        {message && (
          <div className="mb-6">
            <Alert tone={message.type} onDismiss={() => setMessage(null)}>{message.text}</Alert>
          </div>
        )}

        {quizzes.length === 0 ? (
          <Panel className="p-10 text-center text-muted">
            No quizzes yet. Create one here, or upload a JSON file in the format described in the README.
          </Panel>
        ) : (
          <Panel as="ul" className="divide-y divide-line">
            {quizzes.map((quiz) => (
              <li key={quiz.id} className="flex flex-wrap items-center gap-4 px-5 py-4">
                <div className="min-w-0 flex-grow">
                  <h2 className="truncate text-lg font-bold">{quiz.title}</h2>
                  <p className="text-sm text-muted">{quiz.questions.length} {quiz.questions.length === 1 ? 'question' : 'questions'}{quiz.use_timer === false && ', no timer'}</p>
                </div>
                <div className="flex gap-2">
                  <Button variant="ghost" size="sm" onClick={() => deleteQuiz(quiz)} className="hover:!bg-bad-soft hover:!text-bad">Delete</Button>
                  <Button variant="secondary" size="sm" onClick={() => navigate(`/create/${quiz.id}`)}>Edit</Button>
                  <Button size="sm" onClick={() => hostGame(quiz.id)}>Host Game</Button>
                </div>
              </li>
            ))}
          </Panel>
        )}
      </main>
    </div>
  );
}
