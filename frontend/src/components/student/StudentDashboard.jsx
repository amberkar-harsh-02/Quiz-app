import { useState } from 'react';
import HistoryList from './HistoryList';

export default function StudentDashboard({ email, history, historyError, joinError, onJoin, onSignOut, expandedId, onToggle }) {
  const [roomCode, setRoomCode] = useState('');
  const name = email.split('@')[0];

  return (
    <div className="min-h-screen bg-gray-50 px-4 py-6 sm:px-8">
      <div className="mx-auto max-w-3xl">
        <header className="mb-8 flex items-center justify-between gap-4 border-b border-gray-200 pb-6">
          <div className="min-w-0">
            <h1 className="truncate text-2xl font-black text-gray-800 sm:text-3xl">Welcome, {name}</h1>
            <p className="font-bold text-gray-500">Student dashboard</p>
          </div>
          <button onClick={onSignOut} className="shrink-0 rounded-xl border-2 border-gray-300 px-4 py-2 font-bold text-gray-700 transition-colors hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
            Log out
          </button>
        </header>

        <section className="mb-10 rounded-2xl border border-gray-100 bg-white p-5 shadow-sm sm:p-8">
          <h2 className="mb-5 text-xl font-bold text-gray-800 sm:text-2xl">Join a live quiz</h2>
          {joinError && <p role="alert" className="mb-4 rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{joinError}</p>}
          <form
            onSubmit={(e) => { e.preventDefault(); onJoin(roomCode.trim(), name); }}
            className="flex flex-col gap-3 sm:flex-row"
          >
            <label className="sr-only" htmlFor="dashboard-pin">Room PIN</label>
            <input
              id="dashboard-pin"
              type="text"
              required
              autoFocus
              autoComplete="off"
              autoCapitalize="characters"
              maxLength={6}
              placeholder="Room PIN"
              value={roomCode}
              onChange={(e) => setRoomCode(e.target.value.toUpperCase())}
              className="min-w-0 flex-grow rounded-xl bg-gray-100 p-4 font-mono text-2xl font-black tracking-[0.3em] text-gray-800 uppercase focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
            />
            <button type="submit" className="min-h-12 rounded-xl bg-blue-600 px-10 py-4 text-xl font-bold text-white transition-colors hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2">
              Join
            </button>
          </form>
        </section>

        <HistoryList history={history} error={historyError} expandedId={expandedId} onToggle={onToggle} />
      </div>
    </div>
  );
}
