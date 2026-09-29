import { useState } from 'react';
import HistoryList from './HistoryList';
import { Alert, Button, Panel, Wordmark, pinInputClass } from '../ui';

export default function StudentDashboard({ email, history, historyError, joinError, onJoin, onSignOut, expandedId, onToggle }) {
  const [roomCode, setRoomCode] = useState('');
  const name = email.split('@')[0];

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Wordmark title="Quiz App" />
          <div className="flex min-w-0 items-center gap-3">
            <span className="hidden truncate text-sm text-muted sm:inline">{email}</span>
            <Button variant="secondary" size="sm" onClick={onSignOut}>Log out</Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
        <h1 className="mb-6 text-3xl font-bold tracking-tight">Hi, {name}</h1>

        <Panel className="mb-10 p-5 sm:p-6">
          <h2 className="mb-1 text-xl font-bold">Join a live quiz</h2>
          <p className="mb-4 text-muted">Enter the PIN your professor shows on the projector.</p>
          {joinError && <div className="mb-4"><Alert>{joinError}</Alert></div>}
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
              className={`${pinInputClass} min-w-0 flex-grow sm:text-left`}
            />
            <Button type="submit" size="lg" className="sm:w-40">Join</Button>
          </form>
        </Panel>

        <HistoryList history={history} error={historyError} expandedId={expandedId} onToggle={onToggle} />
      </main>
    </div>
  );
}
