import { Button } from '../ui';

export default function Lobby({ roomCode, players, totalPlayers, onStart }) {
  return (
    <div className="flex flex-grow flex-col items-center justify-center text-center">
      <p className="text-3xl text-white/70">Go to <span className="font-bold text-white">{window.location.host}</span> and enter</p>
      <div className="my-6 font-mono text-[7rem] font-extrabold leading-none tracking-[0.15em]">{roomCode}</div>

      <Button size="lg" onClick={onStart} className="mb-12 min-w-72 bg-white !text-stage hover:bg-white/90">
        Start Game ({totalPlayers} {totalPlayers === 1 ? 'Player' : 'Players'})
      </Button>

      {players.length === 0 ? (
        <p className="text-xl text-white/50">Waiting for students to join…</p>
      ) : (
        <ul className="flex max-w-5xl flex-wrap justify-center gap-3" aria-label="Players in the lobby">
          {players.map((p, idx) => (
            <li key={idx} className="rounded-chip bg-white/10 px-5 py-2 text-2xl font-bold motion-safe:animate-pop">{p}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
