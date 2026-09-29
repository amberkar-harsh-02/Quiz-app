import { useEffect, useState } from 'react';
import { ANSWERS } from '../../answers';
import AnswerKey from '../AnswerKey';
import useCountUp from '../useCountUp';
import { Button } from '../ui';

const ordinalRules = new Intl.PluralRules('en', { type: 'ordinal' });
const ORDINAL_SUFFIX = { one: 'st', two: 'nd', few: 'rd', other: 'th' };
const ordinal = (n) => `${n}${ORDINAL_SUFFIX[ordinalRules.select(n)]}`;

// The game runs on the same dark stage as the projector, so primary buttons invert
const ON_STAGE_PRIMARY = 'bg-white !text-stage hover:bg-white/90';

// Milliseconds until `deadline`, refreshed while `running`
function useTimeLeft(deadline, running) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), 200);
    return () => clearInterval(id);
  }, [running]);
  return Math.max(0, deadline - now);
}

function CenteredMessage({ title, children }) {
  return (
    <div className="flex flex-grow flex-col items-center justify-center p-6 text-center motion-safe:animate-rise">
      <h2 className="text-3xl font-bold tracking-tight sm:text-4xl">{title}</h2>
      {children}
    </div>
  );
}

function QuestionView({ game, timeLeft: rawTimeLeft, onAnswer }) {
  const { question, selected, phase } = game;
  // The clock can lag one tick behind a newly arrived question
  const timeLeft = Math.min(rawTimeLeft, question.time_limit * 1000);
  const locked = phase === 'answered' || timeLeft === 0;
  const fraction = timeLeft / (question.time_limit * 1000);
  const urgent = timeLeft <= 5000;

  return (
    <>
      <div className="h-1.5 w-full shrink-0 bg-white/10" role="progressbar" aria-label="Time left" aria-valuemin={0} aria-valuemax={question.time_limit} aria-valuenow={Math.ceil(timeLeft / 1000)}>
        <div
          className={`h-full transition-[width,background-color] duration-200 ease-linear motion-reduce:transition-none ${urgent ? 'bg-[#F97066]' : 'bg-white'}`}
          style={{ width: `${fraction * 100}%` }}
        />
      </div>

      <div className="mx-auto flex w-full max-w-5xl flex-grow flex-col gap-4 p-3 sm:p-6">
        <div className="flex items-start justify-between gap-6 px-1 pt-2">
          <p className="text-xl font-bold leading-snug sm:text-2xl">{question.text}</p>
          <span className={`shrink-0 font-mono text-3xl font-extrabold transition-colors ${urgent ? 'text-[#F97066]' : 'text-white'}`}>
            {Math.ceil(timeLeft / 1000)}
          </span>
        </div>

        <p role="status" className={`min-h-6 px-1 text-white/60 ${locked ? '' : 'invisible'}`}>
          {selected ? 'Answer locked in. Waiting for the others…' : "Time's up. Waiting for results…"}
        </p>

        <div className="grid flex-grow grid-cols-2 gap-3 sm:gap-4">
          {ANSWERS.map(({ color, letter, bg, text }) => {
            const isSelected = selected === color;
            return (
              <button
                key={color}
                onClick={() => onAnswer(color)}
                disabled={locked}
                aria-pressed={isSelected}
                aria-label={`Answer ${letter}`}
                className={`flex min-h-32 items-center justify-center rounded-control transition-[opacity,transform,box-shadow] duration-150 enabled:hover:brightness-110 motion-safe:enabled:active:scale-[0.98]
                  ${isSelected ? 'shadow-lg ring-4 ring-white ring-offset-4 ring-offset-stage' : ''}
                  ${locked && !isSelected ? 'opacity-25' : ''}`}
                style={{ backgroundColor: bg, color: text }}
              >
                <AnswerKey color={color} size="xl" onColor />
              </button>
            );
          })}
        </div>
      </div>
    </>
  );
}

function ResultView({ result }) {
  const answered = result.selected_option !== null;
  const tone = result.correct ? 'bg-ok' : answered ? 'bg-bad' : 'bg-ink';
  const points = useCountUp(result.points_earned);

  return (
    <div className={`flex flex-grow flex-col items-center justify-center gap-6 p-6 text-center text-white ${tone}`}>
      <h2 className="text-5xl font-bold tracking-tight motion-safe:animate-settle">
        {result.correct ? 'Correct' : answered ? 'Incorrect' : 'No answer'}
      </h2>

      {result.correct ? (
        <p className="font-mono text-3xl font-extrabold">
          <span aria-hidden="true">+{points}</span>
          <span className="sr-only">{result.points_earned} points</span>
        </p>
      ) : (
        <div className="flex flex-col items-center gap-3 motion-safe:animate-rise">
          <p className="text-white/80">The answer was</p>
          <AnswerKey color={result.correct_option} size="xl" />
        </div>
      )}

      <p className="text-lg text-white/90">
        You're <span className="font-bold text-white">{ordinal(result.rank)}</span> of {result.total_players}
      </p>
    </div>
  );
}

function GameOverView({ final, isSignedIn, onExit, onReview }) {
  const score = useCountUp(final.score, 900);

  return (
    <CenteredMessage title="Game over">
      <p className="mt-6 font-mono text-6xl font-extrabold">
        <span aria-hidden="true">{score}</span>
        <span className="sr-only">Final score {final.score}</span>
      </p>
      <p className="mt-1 text-white/60">points</p>

      <dl className="mt-8 grid w-full max-w-xs grid-cols-2 divide-x divide-white/15 border-y border-white/15 py-4">
        <div>
          <dt className="text-sm text-white/60">Place</dt>
          <dd className="text-2xl font-bold">{ordinal(final.rank)} <span className="text-base font-normal text-white/60">of {final.total_players}</span></dd>
        </div>
        <div>
          <dt className="text-sm text-white/60">Correct</dt>
          <dd className="text-2xl font-bold">{final.correct_answers} <span className="text-base font-normal text-white/60">of {final.total_questions}</span></dd>
        </div>
      </dl>

      <div className="mt-8 flex w-full max-w-xs flex-col gap-3">
        {isSignedIn && final.session_id && <Button size="lg" onClick={() => onReview(final.session_id)} className={ON_STAGE_PRIMARY}>Review answers</Button>}
        <Button variant="stage" size="lg" onClick={onExit}>Back to menu</Button>
        {!isSignedIn && (
          <p className="mt-2 text-sm text-white/60">
            Sign in with your @csumb.edu account next time to keep your results and review the answers.
          </p>
        )}
      </div>
    </CenteredMessage>
  );
}

export default function GameScreen({ game, isSignedIn, onAnswer, onExit, onReview }) {
  const { phase } = game;
  const inQuestion = phase === 'question' || phase === 'answered';
  const timeLeft = useTimeLeft(game.deadline ?? 0, inQuestion);
  const gameEnded = phase === 'game_over' || phase === 'host_left';

  const leave = () => {
    if (window.confirm('Leave this game? Your score so far stays on the leaderboard, but you can’t answer more questions.')) onExit();
  };

  return (
    <div className="flex min-h-[100dvh] w-full flex-col bg-stage text-white">
      <header className="relative z-10 flex h-14 w-full shrink-0 items-center justify-between gap-3 border-b border-white/10 px-4">
        <div className="min-w-0 truncate font-bold">{game.name}</div>
        {game.question && !gameEnded && (
          <div className="shrink-0 text-sm text-white/60">Question {game.question.index + 1} of {game.question.total}</div>
        )}
        <div className="flex shrink-0 items-center gap-3">
          <div>
            <span className="mr-2 text-sm text-white/60">Score</span>
            <span key={game.score} className="inline-block font-mono font-extrabold motion-safe:animate-bump">{game.score}</span>
          </div>
          {!gameEnded && <Button variant="stage" size="sm" onClick={leave}>Leave</Button>}
        </div>
      </header>

      {game.reconnecting && (
        <div role="status" className="border-b border-warn/30 bg-warn-soft px-4 py-2 text-center text-sm font-bold text-warn motion-safe:animate-slide-down">
          Connection lost. Reconnecting…
        </div>
      )}

      <main aria-live="polite" className="flex flex-grow flex-col">
        {phase === 'waiting' && (
          <CenteredMessage title={game.question ? 'Get ready' : "You're in!"}>
            <p className="mt-3 text-lg text-white/60">
              {game.question ? 'The next question is coming up.' : 'Look for your nickname on the big screen.'}
            </p>
          </CenteredMessage>
        )}

        {inQuestion && <QuestionView game={game} timeLeft={timeLeft} onAnswer={onAnswer} />}

        {phase === 'result' && game.result && <ResultView key={game.question?.index} result={game.result} />}

        {phase === 'game_over' && <GameOverView final={game.final} isSignedIn={isSignedIn} onExit={onExit} onReview={onReview} />}

        {phase === 'host_left' && (
          <CenteredMessage title="Session ended">
            <p className="mb-8 mt-3 text-lg text-white/60">The host closed this game.</p>
            <Button size="lg" className={`w-full max-w-xs ${ON_STAGE_PRIMARY}`} onClick={onExit}>Back to menu</Button>
          </CenteredMessage>
        )}
      </main>
    </div>
  );
}
