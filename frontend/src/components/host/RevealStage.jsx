import { Button } from '../ui';
import SpreadBars from './SpreadBars';

// Same thresholds as the Analytics page
const accuracyTone = (accuracy) => (accuracy >= 70 ? 'text-[#7ED49B]' : accuracy >= 40 ? 'text-[#F2C46D]' : 'text-[#F97066]');

// Shown after each question: an analytics-style card of how the room answered, plus the explanation and top 5
export default function RevealStage({ question, reveal, leaderboard, secondsLeft, onNext, onEnd }) {
  const answered = Object.values(reveal.spread).reduce((a, b) => a + b, 0);
  const accuracy = answered ? Math.round((reveal.spread[reveal.correct_option] / answered) * 100) : 0;
  const players = answered + (reveal.no_answer ?? 0);

  return (
    <div className="mx-auto flex w-full max-w-7xl flex-grow flex-col justify-center gap-8">
      <div className="grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)] gap-6">
        {/* The question, as it appears in Analytics */}
        <section className="rounded-panel border border-white/10 bg-white/5 p-8">
          <div className="mb-3 flex items-baseline justify-between gap-6">
            <p className="text-xl text-white/60">Question {question.index + 1} of {question.total}</p>
            <p className={`text-2xl font-bold ${answered ? accuracyTone(accuracy) : 'text-white/50'}`}>
              {answered ? `${accuracy}% correct` : 'No answers'}
            </p>
          </div>
          <h1 className="mb-8 text-3xl font-bold leading-snug">{question.text}</h1>

          <div className="text-2xl font-bold">
            <SpreadBars
              spread={reveal.spread}
              options={question.options}
              correctOption={reveal.correct_option}
              showPercent
              noAnswer={reveal.no_answer}
              onStage
            />
          </div>

          <p className="mt-6 border-t border-white/10 pt-4 text-lg text-white/60">
            <span className="font-mono font-extrabold text-white">{answered}</span> of {players} answered
          </p>
        </section>

        <div className="flex flex-col gap-6">
          {reveal.explanation && (
            <section className="rounded-panel border border-white/10 bg-white/5 p-6 motion-safe:animate-rise" style={{ animationDelay: '500ms' }}>
              <h2 className="mb-2 text-lg text-white/60">Explanation</h2>
              <p className="text-xl leading-relaxed text-white/90">{reveal.explanation}</p>
            </section>
          )}

          <section className="flex-grow rounded-panel border border-white/10 bg-white/5 p-6">
            <h2 className="mb-3 text-lg text-white/60">Leaderboard</h2>
            {leaderboard.length === 0 ? (
              <p className="text-xl text-white/50">No scores yet.</p>
            ) : (
              <ol className="divide-y divide-white/10">
                {leaderboard.map((player, idx) => (
                  <li
                    key={player.name}
                    className="flex items-baseline gap-4 py-2.5 motion-safe:animate-rise"
                    style={{ animationDelay: `${700 + idx * 60}ms` }}
                  >
                    <span className="w-6 font-mono text-xl font-extrabold text-white/50">{idx + 1}</span>
                    <span className="min-w-0 flex-grow truncate text-xl font-bold">{player.name}</span>
                    <span className="font-mono text-xl font-extrabold">{player.score}</span>
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </div>

      <div className="flex items-center justify-between gap-6 border-t border-white/10 pt-6">
        {/* secondsLeft is null when the results wait for the professor */}
        <p className="text-xl text-white/60">
          {secondsLeft == null ? (
            reveal.is_last_question ? 'That was the last question.' : 'Take your time. Move on when the class is ready.'
          ) : (
            <>
              {reveal.is_last_question ? 'Final results' : 'Next question'} in <span className="font-mono font-extrabold text-white">{secondsLeft}</span>...
            </>
          )}
        </p>
        <div className="flex gap-4">
          {!reveal.is_last_question && (
            <Button variant="stage" onClick={onEnd} className="hover:!bg-[#F97066]/15">End Game Early</Button>
          )}
          {secondsLeft == null ? (
            <Button onClick={onNext} className="bg-white !text-stage hover:bg-white/90">
              {reveal.is_last_question ? 'Show Final Results' : 'Next Question'}
            </Button>
          ) : (
            <Button variant="stage" onClick={onNext}>Skip Delay</Button>
          )}
        </div>
      </div>
    </div>
  );
}
