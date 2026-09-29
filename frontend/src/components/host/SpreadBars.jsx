import { ANSWERS } from '../../answers';
import AnswerKey from '../AnswerKey';

// One row per answer: letter key, optional answer text, a bar sized by how many picked it, and the count.
// `onStage` switches to the dark projector colors.
export default function SpreadBars({ spread, options, correctOption, onStage = false }) {
  const total = Object.values(spread).reduce((a, b) => a + b, 0);
  const track = onStage ? 'bg-white/10' : 'bg-paper';

  return (
    <ul className={onStage ? 'space-y-3' : 'space-y-1.5'}>
      {ANSWERS.map(({ color, bg }) => {
        const count = spread[color];
        const isCorrect = correctOption === color;
        const share = total ? count / total : 0;
        return (
          <li
            key={color}
            className={`grid items-center gap-4 ${options ? 'grid-cols-[minmax(0,2fr)_minmax(0,3fr)_3rem]' : 'grid-cols-[1.5rem_minmax(0,1fr)_2rem]'} ${
              correctOption && !isCorrect ? 'opacity-50 motion-safe:animate-dim' : ''
            }`}
          >
            <div className="flex min-w-0 items-center gap-3">
              <AnswerKey color={color} size={onStage ? 'lg' : 'sm'} />
              {options && <span className="truncate">{options[color]}</span>}
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
          </li>
        );
      })}
    </ul>
  );
}
