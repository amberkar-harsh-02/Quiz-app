import { useEffect, useState } from 'react';
import { ANSWERS, answerFor } from '../../answers';
import AnswerShape from '../AnswerShape';

const ordinalRules = new Intl.PluralRules('en', { type: 'ordinal' });
const ORDINAL_SUFFIX = { one: 'st', two: 'nd', few: 'rd', other: 'th' };
const ordinal = (n) => `${n}${ORDINAL_SUFFIX[ordinalRules.select(n)]}`;

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
    <div className="flex flex-grow flex-col items-center justify-center p-6 text-center">
      <h2 className="text-3xl font-black text-gray-800 sm:text-4xl">{title}</h2>
      {children}
    </div>
  );
}

function PrimaryButton({ onClick, children }) {
  return (
    <button onClick={onClick} className="min-h-12 w-full max-w-xs rounded-xl bg-gray-900 py-4 text-lg font-bold text-white transition-colors hover:bg-gray-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2">
      {children}
    </button>
  );
}

function QuestionView({ game, timeLeft: rawTimeLeft, onAnswer }) {
  const { question, selected, phase } = game;
  // The clock can lag one tick behind a newly arrived question
  const timeLeft = Math.min(rawTimeLeft, question.time_limit * 1000);
  const locked = phase === 'answered' || timeLeft === 0;
  const fraction = timeLeft / (question.time_limit * 1000);

  return (
    <>
      <div className="h-1.5 w-full shrink-0 bg-gray-200" role="progressbar" aria-label="Time left" aria-valuemin={0} aria-valuemax={question.time_limit} aria-valuenow={Math.ceil(timeLeft / 1000)}>
        <div
          className={`h-full transition-[width] duration-200 ease-linear ${timeLeft <= 5000 ? 'bg-red-500' : 'bg-blue-600'}`}
          style={{ width: `${fraction * 100}%` }}
        />
      </div>

      <div className="flex flex-grow flex-col gap-4 p-3 sm:p-4">
        <div className="flex items-start justify-between gap-4 rounded-xl bg-white p-4 shadow-sm">
          <p className="text-lg font-bold text-gray-800 sm:text-xl">{question.text}</p>
          <span className={`shrink-0 font-mono text-2xl font-black tabular-nums ${timeLeft <= 5000 ? 'text-red-600' : 'text-gray-800'}`}>
            {Math.ceil(timeLeft / 1000)}
          </span>
        </div>

        {locked && (
          <p role="status" className="text-center font-bold text-gray-500">
            {selected ? 'Answer locked in. Waiting for the others…' : "Time's up. Waiting for results…"}
          </p>
        )}

        <div className="grid flex-grow grid-cols-1 gap-3 sm:grid-cols-2">
          {ANSWERS.map(({ color, bg, text }) => {
            const isSelected = selected === color;
            return (
              <button
                key={color}
                onClick={() => onAnswer(color)}
                disabled={locked}
                aria-pressed={isSelected}
                className={`flex min-h-16 items-center gap-4 rounded-xl p-4 text-left text-lg font-bold shadow-sm transition focus:outline-none focus-visible:ring-4 focus-visible:ring-gray-900 enabled:hover:brightness-110 enabled:active:scale-[0.98] motion-reduce:transition-none sm:text-xl
                  ${isSelected ? 'ring-4 ring-gray-900 ring-offset-2' : ''}
                  ${locked && !isSelected ? 'opacity-30' : ''}`}
                style={{ backgroundColor: bg, color: text }}
              >
                <AnswerShape color={color} className="h-8 w-8 shrink-0" />
                <span className="break-words">{question.options[color]}</span>
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
  const tone = result.correct ? 'bg-green-600' : answered ? 'bg-red-600' : 'bg-gray-700';
  const correctAnswer = answerFor(result.correct_option);

  return (
    <div className={`flex flex-grow flex-col items-center justify-center gap-6 p-6 text-center text-white ${tone}`}>
      <h2 className="text-4xl font-black sm:text-5xl">
        {result.correct ? 'Correct' : answered ? 'Incorrect' : 'No answer'}
      </h2>

      {result.correct ? (
        <div className="rounded-full bg-black/20 px-6 py-2 text-2xl font-black">+{result.points_earned}</div>
      ) : (
        <div className="flex max-w-md flex-col items-center gap-2">
          <p className="text-sm font-bold uppercase tracking-wider text-white/80">The answer was</p>
          <div className="flex items-center gap-3 rounded-xl bg-white px-5 py-3 text-lg font-bold text-gray-900">
            <span style={{ color: correctAnswer.bg }}><AnswerShape color={result.correct_option} className="h-6 w-6" /></span>
            {result.correct_text}
          </div>
        </div>
      )}

      <p className="text-lg font-bold text-white/90">
        You're {ordinal(result.rank)} of {result.total_players}
      </p>
    </div>
  );
}

function GameOverView({ final, isSignedIn, onExit, onReview }) {
  return (
    <CenteredMessage title="Game over">
      <div className="mt-6 grid w-full max-w-sm grid-cols-2 gap-3">
        <div className="col-span-2 rounded-xl border border-gray-100 bg-white p-5 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-gray-400">Final score</div>
          <div className="text-5xl font-black text-blue-600">{final.score}</div>
        </div>
        <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-gray-400">Place</div>
          <div className="text-2xl font-black text-gray-800">{ordinal(final.rank)} <span className="text-base text-gray-400">of {final.total_players}</span></div>
        </div>
        <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
          <div className="text-xs font-bold uppercase tracking-wider text-gray-400">Correct</div>
          <div className="text-2xl font-black text-gray-800">{final.correct_answers} <span className="text-base text-gray-400">/ {final.total_questions}</span></div>
        </div>
      </div>

      <div className="mt-8 flex w-full flex-col items-center gap-3">
        {isSignedIn && final.session_id && <PrimaryButton onClick={() => onReview(final.session_id)}>Review answers</PrimaryButton>}
        <button onClick={onExit} className="min-h-12 w-full max-w-xs rounded-xl border-2 border-gray-300 py-3 font-bold text-gray-700 transition-colors hover:bg-gray-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
          Back to menu
        </button>
        {!isSignedIn && (
          <p className="mt-2 max-w-xs text-sm font-semibold text-gray-500">
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
    <div className="flex min-h-[100dvh] w-full flex-col bg-gray-50">
      <header className="flex h-14 w-full shrink-0 items-center justify-between gap-3 bg-white px-4 shadow-sm">
        <div className="min-w-0 truncate font-black text-gray-800">{game.name}</div>
        {game.question && !gameEnded && (
          <div className="shrink-0 text-sm font-bold text-gray-500">Q {game.question.index + 1}/{game.question.total}</div>
        )}
        <div className="flex shrink-0 items-center gap-4">
          <div className="font-bold text-blue-600">
            <span className="mr-1 text-xs uppercase text-gray-400">Score</span>{game.score}
          </div>
          {!gameEnded && (
            <button onClick={leave} className="rounded-lg px-2 py-1 text-sm font-bold text-gray-500 hover:bg-gray-100 hover:text-gray-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500">
              Leave
            </button>
          )}
        </div>
      </header>

      {game.reconnecting && (
        <div role="status" className="bg-amber-100 px-4 py-2 text-center text-sm font-bold text-amber-800">
          Connection lost. Reconnecting…
        </div>
      )}

      {phase === 'waiting' && (
        <CenteredMessage title={game.question ? 'Get ready' : "You're in!"}>
          <p className="mt-4 text-lg font-bold text-gray-400">
            {game.question ? 'The next question is coming up.' : 'Look for your nickname on the big screen.'}
          </p>
        </CenteredMessage>
      )}

      {inQuestion && <QuestionView game={game} timeLeft={timeLeft} onAnswer={onAnswer} />}

      {phase === 'result' && game.result && <ResultView result={game.result} />}

      {phase === 'game_over' && <GameOverView final={game.final} isSignedIn={isSignedIn} onExit={onExit} onReview={onReview} />}

      {phase === 'host_left' && (
        <CenteredMessage title="Session ended">
          <p className="mb-8 mt-4 text-lg font-bold text-gray-400">The host closed this game.</p>
          <PrimaryButton onClick={onExit}>Back to menu</PrimaryButton>
        </CenteredMessage>
      )}
    </div>
  );
}
