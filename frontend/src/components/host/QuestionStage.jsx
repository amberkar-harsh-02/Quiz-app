import { ANSWERS } from '../../answers';
import AnswerKey from '../AnswerKey';
import { Button } from '../ui';
import TimerRing from './TimerRing';

export default function QuestionStage({ question, timeLeft, answersCount, totalPlayers, onSkip }) {
  return (
    <div className="flex flex-grow flex-col gap-8">
      <div className="flex items-start justify-between gap-10">
        <div>
          <p className="mb-3 text-xl text-white/60">Question {question.index + 1} of {question.total}</p>
          <h1 className="max-w-5xl text-5xl font-bold leading-tight">{question.text}</h1>
        </div>
        <div className="flex shrink-0 items-center gap-8">
          <div className="text-right">
            <div className="text-white/60">Answers</div>
            <div className="font-mono text-5xl font-extrabold">
              <span key={answersCount} className="inline-block motion-safe:animate-bump">{answersCount}</span>
              <span className="text-white/40">/{totalPlayers}</span>
            </div>
          </div>
          <TimerRing timeLeft={timeLeft} total={question.time_limit} />
        </div>
      </div>

      <div className="grid flex-grow grid-cols-2 gap-5">
        {ANSWERS.map(({ color, bg, text }) => (
          <div
            key={color}
            className="flex items-center gap-6 rounded-control px-8 py-6 text-4xl font-bold"
            style={{ backgroundColor: bg, color: text }}
          >
            <AnswerKey color={color} size="xl" onColor />
            <span>{question.options[color]}</span>
          </div>
        ))}
      </div>

      <div className="flex justify-end">
        <Button variant="stage" size="lg" onClick={onSkip}>Skip Timer</Button>
      </div>
    </div>
  );
}
