import { ANSWERS } from '../../answers';

// Spread looks random but is fixed, so renders are pure and repeatable
const PIECES = Array.from({ length: 60 }, (_, i) => ({
  left: (i * 37) % 100,
  delay: ((i * 53) % 90) / 100,       // 0–0.9 s
  duration: 2.2 + ((i * 29) % 12) / 10, // 2.2–3.3 s
  size: 6 + ((i * 17) % 6),
  color: ANSWERS[i % ANSWERS.length].bg,
  drift: ((i * 41) % 120) - 60,       // px sideways while falling
  round: i % 3 === 0,
}));

// A short burst over the whole screen; pointer-events off so buttons stay clickable
export default function Confetti() {
  return (
    <div className="pointer-events-none fixed inset-0 z-40 overflow-hidden motion-reduce:hidden" aria-hidden="true">
      {PIECES.map((p, i) => (
        <span
          key={i}
          className={`absolute -top-4 block animate-confetti-fall ${p.round ? 'rounded-full' : 'rounded-[2px]'}`}
          style={{
            left: `${p.left}%`,
            width: p.size,
            height: p.round ? p.size : p.size * 1.6,
            backgroundColor: p.color,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
            '--drift': `${p.drift}px`,
          }}
        />
      ))}
    </div>
  );
}
