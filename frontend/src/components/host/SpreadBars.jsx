import { ANSWERS } from '../../answers';
import AnswerKey from '../AnswerKey';

// One row per answer: letter key, optional answer text, a bar sized by how many picked it, the count,
// and optionally its share of the answers given. `noAnswer` adds a row for students who didn't answer
// (needs `options`, since that row has no letter key). `onStage` switches to the dark projector colors.
export default function SpreadBars({ spread, options, correctOption, showPercent = false, noAnswer, onStage = false }) {
  const total = Object.values(spread).reduce((a, b) => a + b, 0);
  const track = onStage ? 'bg-white/10' : 'bg-paper';
  const muted = onStage ? 'text-white/60' : 'text-muted';
  const columns = [
    // With answer texts, the text gets more room than the bar so it isn't cut off
    options ? 'minmax(0,3fr)' : '1.5rem',
    options ? 'minmax(0,2fr)' : 'minmax(0,1fr)',
    onStage ? '3rem' : '2rem',
    ...(showPercent ? [onStage ? '4.5rem' : '3rem'] : []),
  ].join(' ');
  const rowClass = 'grid items-center gap-4';

  return (
    <ul className={onStage ? 'space-y-3' : 'space-y-1.5'}>
      {ANSWERS.map(({ color, bg }) => {
        const count = spread[color];
        const isCorrect = correctOption === color;
        const share = total ? count / total : 0;
        return (
          <li
            key={color}
            className={`${rowClass} ${correctOption && !isCorrect ? 'opacity-50 motion-safe:animate-dim' : ''}`}
            style={{ gridTemplateColumns: columns }}
          >
            <div className="flex min-w-0 items-center gap-3">
              <AnswerKey color={color} size={onStage ? 'lg' : 'sm'} />
              {options && <span className={onStage ? 'min-w-0 break-words leading-tight' : 'truncate'}>{options[color]}</span>}
              {isCorrect && (
                <span className="shrink-0 font-bold text-ok motion-safe:animate-pop" style={{ animationDelay: '300ms', color: onStage ? '#7ED49B' : undefined }}>
                  ✓<span className="sr-only"> correct answer</span>
                </span>
              )}
            </div>
            <div className={`h-full min-h-3 overflow-hidden rounded-chip ${track} ${onStage ? 'min-h-8' : ''}`}>
              <div
                className="h-full origin-left rounded-chip motion-safe:animate-grow-x"
                style={{ width: `${share * 100}%`, backgroundColor: bg }}
              />
            </div>
            <span className="text-right font-mono font-extrabold">{count}</span>
            {showPercent && <span className={`text-right font-mono ${muted}`}>{Math.round(share * 100)}%</span>}
          </li>
        );
      })}

      {options && noAnswer != null && (
        <li className={`${rowClass} ${muted}`} style={{ gridTemplateColumns: columns }}>
          <span className={onStage ? 'pl-[3.25rem]' : 'pl-8'}>No answer</span>
          <span />
          <span className="text-right font-mono font-extrabold">{noAnswer}</span>
          {showPercent && <span />}
        </li>
      )}
    </ul>
  );
}
