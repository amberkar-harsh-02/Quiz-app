const RADIUS = 44;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

// Countdown ring for the projector. The host timer ticks once a second, so the stroke
// eases over one second to drain smoothly between ticks.
export default function TimerRing({ timeLeft, total }) {
  const fraction = total ? timeLeft / total : 0;
  const urgent = timeLeft <= 5;

  return (
    <div className="relative h-28 w-28 shrink-0" role="timer" aria-label={`${timeLeft} seconds left`}>
      <svg viewBox="0 0 100 100" className="h-full w-full -rotate-90" aria-hidden="true">
        <circle cx="50" cy="50" r={RADIUS} fill="none" strokeWidth="8" className="stroke-white/15" />
        <circle
          cx="50" cy="50" r={RADIUS} fill="none" strokeWidth="8" strokeLinecap="round"
          strokeDasharray={CIRCUMFERENCE}
          strokeDashoffset={CIRCUMFERENCE * (1 - fraction)}
          className={`transition-[stroke-dashoffset,stroke] duration-1000 ease-linear motion-reduce:transition-none ${urgent ? 'stroke-[#F97066]' : 'stroke-white'}`}
        />
      </svg>
      <span className={`absolute inset-0 flex items-center justify-center font-mono text-4xl font-extrabold ${urgent ? 'text-[#F97066]' : 'text-white'}`} aria-hidden="true">
        {timeLeft}
      </span>
    </div>
  );
}
