import { Wordmark } from '../ui';

// Dark projector frame shared by every live-game view on the host screen
export default function Stage({ roomCode, playerCount, children }) {
  return (
    <div className="flex min-h-screen flex-col bg-stage text-white">
      <header className="flex items-center justify-between gap-6 border-b border-white/10 px-8 py-4">
        <Wordmark title="Quiz App" />
        {roomCode && (
          <div className="flex items-center gap-8 text-white/70">
            <span>PIN <span className="ml-2 font-mono text-xl font-extrabold tracking-[0.2em] text-white">{roomCode}</span></span>
            <span><span className="font-mono text-xl font-extrabold text-white">{playerCount}</span> {playerCount === 1 ? 'player' : 'players'}</span>
          </div>
        )}
      </header>
      <main className="flex flex-grow flex-col px-8 py-8">{children}</main>
    </div>
  );
}
