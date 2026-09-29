import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch, readToken } from '../api';
import { Alert, Button, Panel, Wordmark } from '../components/ui';
import SpreadBars from '../components/host/SpreadBars';

export default function AnalyticsDashboard() {
  const [sessions, setSessions] = useState([]);
  const [selectedSession, setSelectedSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const navigate = useNavigate();

  // Fetch all past sessions on load
  useEffect(() => {
    if (!readToken()) { navigate('/'); return; }

    apiFetch('/sessions/')
      .then(setSessions)
      .catch(err => setError(`Couldn't load sessions: ${err.message}`))
      .finally(() => setLoading(false));
  }, [navigate]);

  // Fetch detailed analytics for a specific session
  const viewSession = (sessionId) => {
    setLoading(true);
    setError('');
    apiFetch(`/analytics/${sessionId}`)
      .then(setSelectedSession)
      .catch(err => setError(`Couldn't load this session: ${err.message}`))
      .finally(() => setLoading(false));
  };

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-xl text-muted">Loading Analytics...</div>;
  }

  const accuracyTone = (accuracy) => (accuracy >= 70 ? 'text-ok' : accuracy >= 40 ? 'text-warn' : 'text-bad');

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-6 py-3">
          <Wordmark title="Quiz App" />
          <Button variant="secondary" size="sm" onClick={() => navigate('/host')}>Exit to Dashboard</Button>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-6 py-8">
        <div className="mb-6 flex flex-wrap items-center gap-4">
          {selectedSession && (
            <Button variant="ghost" size="sm" onClick={() => setSelectedSession(null)}>&larr; Back to Archive</Button>
          )}
          <h1 className="text-3xl font-bold tracking-tight">{selectedSession ? selectedSession.quiz_title : 'Analytics'}</h1>
        </div>

        {error && <div className="mb-6"><Alert>{error}</Alert></div>}

        {/* VIEW 1: Session Archive (Master List) */}
        {!selectedSession && (
          <section>
            <h2 className="mb-4 text-xl font-bold">Past Game Sessions</h2>
            {sessions.length === 0 ? (
              <Panel className="p-10 text-center text-muted">
                No sessions yet. Results appear here after you host a game and it ends.
              </Panel>
            ) : (
              <Panel className="overflow-hidden">
                <table className="w-full text-left">
                  <thead className="border-b border-line bg-paper text-sm text-muted">
                    <tr>
                      <th scope="col" className="px-5 py-3 font-bold">Quiz</th>
                      <th scope="col" className="px-5 py-3 font-bold">Room</th>
                      <th scope="col" className="px-5 py-3 text-right font-bold">Students</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {sessions.map((session) => (
                      <tr key={session.id} className="transition-colors hover:bg-paper">
                        <td className="px-5 py-3">
                          <button onClick={() => viewSession(session.id)} className="rounded-chip text-left font-bold text-brand hover:underline">
                            {session.quiz_title}
                          </button>
                        </td>
                        <td className="px-5 py-3 font-mono text-muted">{session.room_code}</td>
                        <td className="px-5 py-3 text-right font-mono">{session.player_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Panel>
            )}
          </section>
        )}

        {/* VIEW 2: Detailed Session Report */}
        {selectedSession && (
          <div className="space-y-8">
            <dl className="grid grid-cols-3 divide-x divide-line rounded-panel border border-line bg-white">
              <div className="px-6 py-4">
                <dt className="text-sm text-muted">Students</dt>
                <dd className="font-mono text-3xl font-extrabold">{selectedSession.overview.total_students}</dd>
              </div>
              <div className="px-6 py-4">
                <dt className="text-sm text-muted">Average score</dt>
                <dd className="font-mono text-3xl font-extrabold">{selectedSession.overview.average_score}</dd>
              </div>
              <div className="px-6 py-4">
                <dt className="text-sm text-muted">Class accuracy</dt>
                <dd className={`font-mono text-3xl font-extrabold ${accuracyTone(selectedSession.overview.average_accuracy)}`}>
                  {selectedSession.overview.average_accuracy}%
                </dd>
              </div>
            </dl>

            <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
              {/* Question Breakdown (Identify struggle areas) */}
              <section className="lg:col-span-2">
                <h2 className="mb-4 text-xl font-bold">Question Performance</h2>
                <Panel as="ol" className="divide-y divide-line">
                  {selectedSession.questions.map((q, idx) => (
                    <li key={q.question_id} className="p-5">
                      <div className="mb-3 flex items-start justify-between gap-4">
                        <h3 className="font-bold"><span className="mr-2 font-mono text-muted">{idx + 1}.</span>{q.text}</h3>
                        <span className={`shrink-0 font-bold ${accuracyTone(q.accuracy)}`}>{q.accuracy}% correct</span>
                      </div>
                      <SpreadBars spread={q.spread} />
                    </li>
                  ))}
                </Panel>
              </section>

              {/* Student Roster */}
              <section>
                <h2 className="mb-4 text-xl font-bold">Student Roster</h2>
                <Panel className="overflow-hidden">
                  <div className="max-h-[600px] overflow-y-auto">
                    <table className="w-full text-left">
                      <thead className="sticky top-0 border-b border-line bg-paper text-sm text-muted">
                        <tr>
                          <th scope="col" className="px-4 py-3 font-bold">Name</th>
                          <th scope="col" className="px-4 py-3 text-right font-bold">Score</th>
                          <th scope="col" className="px-4 py-3 text-right font-bold">Accuracy</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-line">
                        {selectedSession.students.map((s, idx) => (
                          <tr key={idx}>
                            <td className="px-4 py-3 font-bold">{s.name}</td>
                            <td className="px-4 py-3 text-right font-mono">{s.final_score}</td>
                            <td className={`px-4 py-3 text-right font-mono font-bold ${accuracyTone(s.accuracy)}`}>{s.accuracy}%</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Panel>
              </section>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
