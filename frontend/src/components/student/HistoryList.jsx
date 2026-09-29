import { answerFor } from '../../answers';
import AnswerShape from '../AnswerShape';
import { Alert, Panel } from '../ui';

const dateFormat = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' });

// The server stores naive UTC timestamps
const formatDate = (iso) => (iso ? dateFormat.format(new Date(`${iso}Z`)) : '');

function accuracyClass(accuracy) {
  if (accuracy >= 70) return 'bg-ok-soft text-ok';
  if (accuracy >= 40) return 'bg-warn-soft text-warn';
  return 'bg-bad-soft text-bad';
}

function AnswerLine({ label, color, text, tone }) {
  const answer = answerFor(color);
  return (
    <div className={`flex items-start gap-3 rounded-chip border px-3 py-2 ${tone}`}>
      {answer && <span className="mt-0.5 shrink-0" style={{ color: answer.bg }}><AnswerShape color={color} className="h-4 w-4" /></span>}
      <div>
        <div className="text-sm text-muted">{label}</div>
        <div className="font-bold">{text}</div>
      </div>
    </div>
  );
}

function AnswerReview({ q, number }) {
  return (
    <li className="border-t border-line py-5 first:border-t-0 first:pt-0 last:pb-0">
      <h4 className="mb-3 font-bold"><span className="mr-2 font-mono text-muted">{number}.</span>{q.question_text}</h4>

      <div className="mb-3 grid grid-cols-1 gap-2 md:grid-cols-2">
        <AnswerLine
          label={q.is_correct ? 'Your answer (correct)' : 'Your answer'}
          color={q.selected_option}
          text={q.selected_text}
          tone={q.is_correct ? 'border-ok/30 bg-ok-soft' : 'border-bad/30 bg-bad-soft'}
        />
        {!q.is_correct && <AnswerLine label="Correct answer" color={q.correct_option} text={q.correct_text} tone="border-line bg-white" />}
      </div>

      <p className="border-l-2 border-brand pl-3 text-muted">{q.explanation}</p>
    </li>
  );
}

export default function HistoryList({ history, error, expandedId, onToggle }) {
  const averageAccuracy = history.length
    ? Math.round(history.reduce((sum, s) => sum + s.accuracy, 0) / history.length)
    : 0;

  return (
    <section>
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
        <h2 className="text-xl font-bold">Past quizzes</h2>
        {history.length > 0 && (
          <p className="text-muted">
            <span className="font-bold text-ink">{history.length}</span> played, <span className="font-bold text-ink">{averageAccuracy}%</span> average accuracy
          </p>
        )}
      </div>

      {error && <div className="mb-4"><Alert>Couldn't load your history: {error}</Alert></div>}

      {history.length === 0 ? (
        !error && (
          <Panel className="p-8 text-center text-muted">
            Quizzes you play while signed in show up here, with the answers and explanations.
          </Panel>
        )
      ) : (
        <Panel as="ul" className="divide-y divide-line overflow-hidden">
          {history.map((session) => {
            const expanded = expandedId === session.session_id;
            return (
              <li key={session.id}>
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => onToggle(session.session_id)}
                  className="flex w-full items-center gap-4 px-5 py-4 text-left transition-colors hover:bg-paper focus-visible:ring-inset focus-visible:ring-offset-0"
                >
                  <div className="min-w-0 flex-grow">
                    <h3 className="truncate font-bold">{session.quiz_title}</h3>
                    <p className="text-sm text-muted">{formatDate(session.played_at)}</p>
                  </div>
                  <dl className="hidden shrink-0 text-right sm:flex sm:gap-6">
                    <div>
                      <dt className="text-xs text-muted">Score</dt>
                      <dd className="font-mono font-bold">{session.total_score}</dd>
                    </div>
                    <div>
                      <dt className="text-xs text-muted">Correct</dt>
                      <dd className="font-mono font-bold">{session.correct_answers}/{session.total_questions}</dd>
                    </div>
                  </dl>
                  <span className={`w-14 shrink-0 rounded-chip py-1 text-center text-sm font-bold ${accuracyClass(session.accuracy)}`}>{session.accuracy}%</span>
                  <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" className={`h-5 w-5 shrink-0 text-muted transition-transform duration-200 motion-reduce:transition-none ${expanded ? 'rotate-180' : ''}`}>
                    <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                  </svg>
                </button>

                {/* Always rendered so the height can animate; inert keeps it out of tab order while closed */}
                <div
                  inert={!expanded}
                  className={`grid transition-[grid-template-rows] duration-200 ease-out motion-reduce:transition-none ${expanded ? 'grid-rows-[1fr]' : 'grid-rows-[0fr]'}`}
                >
                  <div className="overflow-hidden">
                    <div className="border-t border-line bg-paper/60 px-5 py-5">
                      {session.details.length === 0 ? (
                        <p className="text-muted">You didn't answer any questions in this game.</p>
                      ) : (
                        <ol>
                          {session.details.map((q, idx) => <AnswerReview key={idx} q={q} number={idx + 1} />)}
                        </ol>
                      )}
                    </div>
                  </div>
                </div>
              </li>
            );
          })}
        </Panel>
      )}
    </section>
  );
}
