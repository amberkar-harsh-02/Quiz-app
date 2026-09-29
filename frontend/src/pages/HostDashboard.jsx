import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { WS_URL, apiFetch, clearToken, getToken, readToken } from '../api';
import { ANSWERS } from '../answers';
import AnswerShape from '../components/AnswerShape';

export default function HostDashboard() {
  const [quizzes, setQuizzes] = useState([]);
  const [view, setView] = useState('dashboard'); // dashboard, lobby, question, leaderboard, game_over
  const [roomCode, setRoomCode] = useState('');
  const [players, setPlayers] = useState([]);
  const [totalPlayers, setTotalPlayers] = useState(0);
  const [message, setMessage] = useState(null); // { type: 'error' | 'success', text }

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
        setView('lobby');
      } else if (data.event === 'player_joined') {
        setPlayers(prev => [...prev, data.student_name]);
        setTotalPlayers(data.total_players);
      } else if (data.event === 'player_left' || data.event === 'player_rejoined') {
        setTotalPlayers(data.total_players);
        setAnswersCount(data.answers_submitted);
      } else if (data.event === 'show_question') {
        setCurrentQuestion(data.question);
        setTimeLeft(data.question.time_limit);
        setAnswersCount(0);
        setView('question');
      } else if (data.event === 'answer_received') {
        setAnswersCount(data.answers_submitted);
        setTotalPlayers(data.total_players);
      } else if (data.event === 'leaderboard') {
        setLeaderboard(data.top_players.slice(0, 3));
        setReveal(data);
        // Leave time to read the explanation out
        setLeaderboardTimeLeft(data.explanation ? 10 : 5);
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

  const answeredTotal = reveal ? Object.values(reveal.spread).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="flex min-h-screen flex-col bg-gray-50 p-8">

      {/* 1. Professor Quiz Dashboard */}
      {view === 'dashboard' && (
        <div className="mx-auto w-full max-w-6xl">
          <div className="mb-10 flex flex-wrap items-center justify-between gap-4 border-b pb-6">
            <h1 className="text-4xl font-black text-gray-800">My Quizzes</h1>
            <div className="flex flex-wrap items-center gap-4">
              <button onClick={() => navigate('/analytics')} className="rounded-lg border-2 border-gray-300 px-6 py-3 font-bold text-gray-700 transition-colors hover:bg-gray-100">
                View Analytics
              </button>

              <input type="file" accept=".json" ref={fileInputRef} onChange={handleFileUpload} className="hidden" />
              <button onClick={() => fileInputRef.current.click()} className="rounded-lg bg-green-600 px-6 py-3 font-bold text-white transition-colors hover:bg-green-700">
                Upload JSON
              </button>

              <button onClick={() => navigate('/create')} className="rounded-lg bg-blue-600 px-6 py-3 font-bold text-white transition-colors hover:bg-blue-700">
                + Create Quiz
              </button>
              <button onClick={() => { clearToken(); navigate('/'); }} className="text-gray-500 hover:underline">
                Log Out
              </button>
            </div>
          </div>

          {message && (
            <div role={message.type === 'error' ? 'alert' : 'status'} className={`mb-8 flex items-start justify-between gap-4 rounded-xl p-4 font-bold ${message.type === 'error' ? 'bg-red-50 text-red-700' : 'bg-green-50 text-green-700'}`}>
              <span>{message.text}</span>
              <button onClick={() => setMessage(null)} aria-label="Dismiss" className="text-xl leading-none opacity-60 hover:opacity-100">×</button>
            </div>
          )}

          <div className="grid grid-cols-1 gap-8 md:grid-cols-2 lg:grid-cols-3">
            {quizzes.length === 0 ? (
              <div className="col-span-full rounded-xl bg-white p-12 text-center text-xl text-gray-500 shadow-sm">
                You haven't created any quizzes yet. Click the blue button above to get started!
              </div>
            ) : (
              quizzes.map((quiz) => (
                <div key={quiz.id} className="flex flex-col rounded-2xl bg-white p-8 shadow-md border border-gray-100">
                  <h2 className="mb-1 text-2xl font-bold text-gray-800">{quiz.title}</h2>
                  <p className="mb-6 font-semibold text-gray-400">{quiz.questions.length} {quiz.questions.length === 1 ? 'question' : 'questions'}</p>
                  <div className="mt-auto flex flex-col space-y-3">
                    <button onClick={() => hostGame(quiz.id)} className="rounded-lg bg-green-600 py-3 font-bold text-white hover:bg-green-700">
                      Host Game
                    </button>
                    <div className="flex space-x-3">
                      <button onClick={() => navigate(`/create/${quiz.id}`)} className="flex-1 rounded-lg border-2 border-gray-200 py-2 font-bold text-gray-600 hover:bg-gray-50">
                        Edit
                      </button>
                      <button onClick={() => deleteQuiz(quiz)} className="flex-1 rounded-lg bg-red-100 py-2 font-bold text-red-600 hover:bg-red-200">
                        Delete
                      </button>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* 2. Game Lobby */}
      {view === 'lobby' && (
        <div className="flex flex-grow flex-col items-center justify-center text-center">
          <h2 className="mb-4 text-3xl font-bold text-gray-600">Join at <span className="text-blue-600">{window.location.host}</span> with PIN</h2>
          <div className="mb-10 font-mono text-9xl font-black tracking-widest text-gray-900">{roomCode}</div>
          <button onClick={startGame} className="mb-10 rounded-xl bg-green-600 px-12 py-5 text-3xl font-bold text-white shadow-lg hover:bg-green-700">
            Start Game ({totalPlayers} {totalPlayers === 1 ? 'Player' : 'Players'})
          </button>
          <div className="flex max-w-4xl flex-wrap justify-center gap-4">
            {players.map((p, idx) => (
              <span key={idx} className="rounded-full bg-blue-100 px-6 py-2 text-xl font-semibold text-blue-800">{p}</span>
            ))}
          </div>
        </div>
      )}

      {/* 3. Question View */}
      {view === 'question' && currentQuestion && (
        <div className="flex flex-grow flex-col">
          <div className="mb-8 flex items-center justify-between gap-8 rounded-2xl bg-white p-8 shadow-md">
            <div>
              <div className="mb-2 text-sm font-bold uppercase tracking-wider text-gray-400">Question {currentQuestion.index + 1} of {currentQuestion.total}</div>
              <h2 className="text-4xl font-bold text-gray-800">{currentQuestion.text}</h2>
            </div>
            <div className="flex shrink-0 items-center space-x-8">
              <div className="text-right">
                <div className="text-sm font-bold text-gray-400 uppercase tracking-wider">Answers</div>
                <div className="text-4xl font-black text-blue-600">{answersCount} / {totalPlayers}</div>
              </div>
              <div className={`flex h-24 w-24 items-center justify-center rounded-full text-4xl font-black text-white ${timeLeft <= 5 ? 'bg-red-500 animate-pulse motion-reduce:animate-none' : 'bg-gray-800'}`}>
                {timeLeft}
              </div>
            </div>
          </div>

          <div className="grid flex-grow grid-cols-2 gap-6">
            {ANSWERS.map(({ color, bg, text }) => (
              <div
                key={color}
                className="relative flex items-center rounded-2xl p-8 text-4xl font-bold shadow-md"
                style={{ backgroundColor: bg, color: text }}
              >
                <AnswerShape color={color} className="mr-6 h-14 w-14 shrink-0 opacity-90" />
                <span>{currentQuestion.options[color]}</span>
              </div>
            ))}
          </div>

          <div className="mt-8 flex justify-end">
            <button onClick={showLeaderboard} className="rounded-xl bg-gray-900 px-10 py-4 text-xl font-bold text-white hover:bg-gray-800">
              Skip Timer
            </button>
          </div>
        </div>
      )}

      {/* 4. Answer Reveal + Top 3 Leaderboard (Auto-advances) */}
      {view === 'leaderboard' && reveal && currentQuestion && (
        <div className="mx-auto flex w-full max-w-5xl flex-grow flex-col justify-center">
          <h2 className="mb-6 text-center text-4xl font-bold text-gray-800">{currentQuestion.text}</h2>

          {/* Answer spread: one bar per option, correct one highlighted */}
          <div className="mb-6 grid grid-cols-2 gap-4">
            {ANSWERS.map(({ color, bg, text }) => {
              const count = reveal.spread[color];
              const isCorrect = reveal.correct_option === color;
              return (
                <div
                  key={color}
                  className={`relative flex items-center gap-4 overflow-hidden rounded-xl p-5 text-2xl font-bold ${isCorrect ? 'ring-4 ring-gray-900 ring-offset-2' : 'opacity-40'}`}
                  style={{ backgroundColor: bg, color: text }}
                >
                  <div className="absolute inset-y-0 left-0 bg-black/20" style={{ width: `${answeredTotal ? (count / answeredTotal) * 100 : 0}%` }} />
                  <AnswerShape color={color} className="relative h-8 w-8 shrink-0" />
                  <span className="relative flex-grow">{currentQuestion.options[color]}</span>
                  <span className="relative font-black">{count}</span>
                  {isCorrect && <span className="relative text-3xl" aria-label="Correct answer">✓</span>}
                </div>
              );
            })}
          </div>

          {reveal.explanation && (
            <div className="mb-10 rounded-xl bg-white p-6 shadow-sm">
              <div className="mb-1 text-sm font-bold uppercase tracking-wider text-gray-400">Explanation</div>
              <p className="text-2xl font-semibold text-gray-800">{reveal.explanation}</p>
            </div>
          )}

          <h3 className="mb-4 text-center text-2xl font-black text-gray-500 uppercase tracking-wider">Top 3</h3>
          <div className="space-y-3">
            {leaderboard.length === 0 ? (
              <p className="text-center text-2xl text-gray-500">No scores yet!</p>
            ) : (
              leaderboard.map((player, idx) => (
                <div key={player.name} className="flex items-center justify-between rounded-2xl bg-white p-5 shadow-md">
                  <div className="flex items-center space-x-6">
                    <span className="text-3xl font-black text-gray-400">#{idx + 1}</span>
                    <span className="text-2xl font-bold text-gray-800">{player.name}</span>
                  </div>
                  <span className="text-2xl font-black text-blue-600">{player.score} pts</span>
                </div>
              ))
            )}
          </div>

          {/* Visual indicator of the automatic transition */}
          <div className="mt-10 flex flex-col items-center space-y-6">
            <div className="text-2xl font-bold text-gray-500">
              {reveal.is_last_question ? 'Final results' : 'Next question'} in {leaderboardTimeLeft}...
            </div>
            <div className="flex space-x-6">
              <button onClick={nextQuestion} className="rounded-xl border-2 border-gray-300 px-8 py-3 text-lg font-bold text-gray-600 hover:bg-gray-100">Skip Delay</button>
              {!reveal.is_last_question && (
                <button onClick={endGame} className="rounded-xl bg-red-100 px-8 py-3 text-lg font-bold text-red-600 hover:bg-red-200">End Game Early</button>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 5. Game Over */}
      {view === 'game_over' && (
        <div className="flex flex-grow flex-col items-center justify-center text-center">
          <h2 className="mb-6 text-7xl font-black text-gray-800">Game Over!</h2>
          <p className="mb-12 text-2xl text-gray-600">
            {savedSessionId ? 'Scores have been saved. You can review them in Analytics.' : 'No questions were played, so nothing was saved.'}
          </p>
          <div className="flex gap-4">
            <button
              onClick={() => {
                ws.current?.close();
                loadQuizzes().catch(() => {});
                setView('dashboard');
              }}
              className="rounded-xl bg-blue-600 px-12 py-5 text-2xl font-bold text-white hover:bg-blue-700"
            >
              Return to Dashboard
            </button>
            {savedSessionId && (
              <button onClick={() => navigate('/analytics')} className="rounded-xl border-2 border-gray-300 px-12 py-5 text-2xl font-bold text-gray-700 hover:bg-gray-100">
                View Analytics
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
