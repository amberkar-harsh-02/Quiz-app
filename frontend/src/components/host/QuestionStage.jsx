import { assetUrl } from '../../api';
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
          {question.time_limit != null && <TimerRing timeLeft={timeLeft} total={question.time_limit} />}
        </div>
      </div>

      {/* With an image, the image takes the left half and the answers stack on the right,
          so everything still fits on one projector screen */}
      <div className={`grid flex-grow gap-5 ${question.image_url ? 'grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]' : ''}`}>
        {question.image_url && (
          <div className="flex min-h-0 items-center justify-center rounded-panel border border-white/10 bg-white/5 p-3">
            <img src={assetUrl(question.image_url)} alt={question.image_alt || ''} className="max-h-[55vh] w-auto max-w-full rounded-chip object-contain" />
          </div>
        )}

        <div className={`grid gap-5 ${question.image_url ? 'grid-cols-1' : 'grid-cols-2'}`}>
          {ANSWERS.map(({ color, bg, text }) => (
            <div
              key={color}
              className={`flex items-center gap-6 rounded-control font-bold ${question.image_url ? 'px-6 py-3 text-3xl' : 'px-8 py-6 text-4xl'}`}
              style={{ backgroundColor: bg, color: text }}
            >
              <AnswerKey color={color} size={question.image_url ? 'lg' : 'xl'} onColor />
              <span>{question.options[color]}</span>
            </div>
          ))}
        </div>
      </div>

      <div className="flex justify-end">
        {question.time_limit != null ? (
          <Button variant="stage" size="lg" onClick={onSkip}>Skip Timer</Button>
        ) : (
          <Button size="lg" onClick={onSkip} className="bg-white !text-stage hover:bg-white/90">Show Results</Button>
        )}
      </div>
    </div>
  );
}
