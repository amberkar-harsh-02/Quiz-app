import { Button } from '../ui';
import SpreadBars from './SpreadBars';

// Shown after each question: how the room answered, why, and the top 3
export default function RevealStage({ question, reveal, leaderboard, secondsLeft, onNext, onEnd }) {
  return (
    <div className="mx-auto flex w-full max-w-6xl flex-grow flex-col justify-center gap-10">
      <h1 className="text-4xl font-bold leading-tight">{question.text}</h1>

      <div className="text-3xl font-bold">
        <SpreadBars spread={reveal.spread} options={question.options} correctOption={reveal.correct_option} onStage />
      </div>

      {reveal.explanation && (
        <p className="border-l-4 border-white/40 pl-5 text-2xl leading-relaxed text-white/85 motion-safe:animate-rise" style={{ animationDelay: '500ms' }}>
          {reveal.explanation}
        </p>
      )}

      <section aria-label="Top 3">
        {leaderboard.length === 0 ? (
          <p className="text-2xl text-white/50">No scores yet.</p>
        ) : (
          <ol className="grid grid-cols-3 gap-x-12 gap-y-4">
            {leaderboard.map((player, idx) => (
              <li
                key={player.name}
                className="flex items-baseline gap-4 border-t-2 border-white/20 pt-4 motion-safe:animate-rise"
                style={{ animationDelay: `${700 + idx * 60}ms` }}
              >
                <span className="font-mono text-2xl font-extrabold text-white/50">{idx + 1}</span>
                <span className="min-w-0 flex-grow truncate text-2xl font-bold">{player.name}</span>
                <span className="font-mono text-2xl font-extrabold">{player.score}</span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <div className="flex items-center justify-between gap-6 border-t border-white/10 pt-6">
        {/* secondsLeft is null after a question without a timer: wait for the professor */}
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
