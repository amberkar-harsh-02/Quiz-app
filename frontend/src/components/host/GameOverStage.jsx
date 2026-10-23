import { useEffect, useState } from 'react';
import { Button } from '../ui';
import Confetti from './Confetti';

const prefersReducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const ordinal = (n) => `${n}${{ 1: 'st', 2: 'nd', 3: 'rd' }[n] ?? 'th'}`;

// Podium order on screen is 2nd, 1st, 3rd; revealed 3rd, then 2nd, then 1st
const SLOTS = [
  { place: 1, column: 2, height: 'h-[24vh]', delay: 1.9 },
  { place: 2, column: 1, height: 'h-[17vh]', delay: 1.1 },
  { place: 3, column: 3, height: 'h-[12vh]', delay: 0.3 },
];

function Podium({ players }) {
  return (
    <ol className="mb-8 grid w-full max-w-4xl grid-cols-3 items-end gap-5" aria-label="Top 3">
      {SLOTS.map((slot, i) => {
        const player = players[i];
        if (!player) return <li key={slot.place} style={{ gridColumn: slot.column }} />;
        return (
          <li key={slot.place} className="flex flex-col items-center gap-3" style={{ gridColumn: slot.column }}>
            <div className="text-center motion-safe:animate-pop" style={{ animationDelay: `${slot.delay + 0.35}s` }}>
              <div className={`truncate font-bold ${slot.place === 1 ? 'text-4xl' : 'text-3xl'}`}>{player.name}</div>
              <div className="font-mono text-2xl font-extrabold text-white/70">{player.score}</div>
            </div>
            <div
              className={`flex w-full origin-bottom items-start justify-center rounded-t-panel pt-4 motion-safe:animate-rise-up ${slot.height} ${
                slot.place === 1 ? 'bg-white text-stage' : 'bg-white/15 text-white'
              }`}
              style={{ animationDelay: `${slot.delay}s` }}
            >
              <span className="font-mono text-5xl font-extrabold">{ordinal(player.rank)}</span>
            </div>
          </li>
        );
      })}
    </ol>
  );
}

export default function GameOverStage({ saved, topPlayers = [], onDashboard, onAnalytics }) {
  // Confetti once 1st place is revealed, then removed; never under reduced motion
  const [confetti, setConfetti] = useState(false);
  useEffect(() => {
    if (!topPlayers.length || prefersReducedMotion()) return;
    const show = setTimeout(() => setConfetti(true), 2400);
    const hide = setTimeout(() => setConfetti(false), 6500);
    return () => { clearTimeout(show); clearTimeout(hide); };
  }, [topPlayers.length]);

  return (
    <div className="flex flex-grow flex-col items-center justify-center text-center">
      {confetti && <Confetti />}
      <h1 className="mb-6 text-6xl font-bold tracking-tight motion-safe:animate-rise">Game Over!</h1>

      {topPlayers.length > 0 && <Podium players={topPlayers} />}

      <p className="mb-6 text-xl text-white/70">
        {saved ? 'Scores have been saved. You can review them in Analytics.' : 'No questions were played, so nothing was saved.'}
      </p>
      <div className="flex gap-4">
        <Button size="lg" onClick={onDashboard} className="bg-white !text-stage hover:bg-white/90">Return to Dashboard</Button>
        {saved && <Button variant="stage" size="lg" onClick={onAnalytics}>View Analytics</Button>}
      </div>
    </div>
  );
}
