const dateFormat = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' });

// The server stores naive UTC timestamps
const formatDate = (iso) => (iso ? dateFormat.format(new Date(`${iso}Z`)) : '');

function accuracyClass(accuracy) {
  if (accuracy >= 70) return 'bg-green-100 text-green-700';
  if (accuracy >= 40) return 'bg-yellow-100 text-yellow-800';
  return 'bg-red-100 text-red-700';
}

function Stat({ label, value }) {
  return (
    <div className="rounded-2xl border border-gray-100 bg-white p-5 shadow-sm">
      <div className="text-xs font-bold uppercase tracking-wider text-gray-400">{label}</div>
      <div className="mt-1 text-3xl font-black text-gray-800">{value}</div>
    </div>
  );
}

function AnswerReview({ q, number }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5">
      <h4 className="mb-4 font-bold text-gray-800"><span className="mr-2 text-gray-400">{number}.</span>{q.question_text}</h4>

      <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2">
        <div className={`rounded-lg border-2 p-3 ${q.is_correct ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
          <p className="mb-1 text-xs font-bold uppercase tracking-wider text-gray-500">Your answer</p>
          <p className={`font-bold ${q.is_correct ? 'text-green-700' : 'text-red-700'}`}>{q.selected_text}</p>
        </div>
        {!q.is_correct && (
          <div className="rounded-lg border-2 border-blue-200 bg-blue-50 p-3">
            <p className="mb-1 text-xs font-bold uppercase tracking-wider text-gray-500">Correct answer</p>
            <p className="font-bold text-blue-700">{q.correct_text}</p>
          </div>
        )}
      </div>

      <div className="rounded-lg bg-gray-100 p-3">
        <p className="mb-1 text-xs font-bold uppercase tracking-wider text-gray-500">Explanation</p>
        <p className="text-sm font-semibold text-gray-700">{q.explanation}</p>
      </div>
    </div>
  );
}

export default function HistoryList({ history, error, expandedId, onToggle }) {
  const averageAccuracy = history.length
    ? Math.round(history.reduce((sum, s) => sum + s.accuracy, 0) / history.length)
    : 0;

  return (
    <section>
      <h2 className="mb-5 text-xl font-bold text-gray-800 sm:text-2xl">Past quizzes</h2>

      {error && <p role="alert" className="mb-4 rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">Couldn't load your history: {error}</p>}

      {history.length === 0 ? (
        !error && (
          <div className="rounded-2xl border border-gray-100 bg-white p-10 text-center font-bold text-gray-400">
            You haven't played any quizzes yet.
          </div>
        )
      ) : (
        <>
          <div className="mb-6 grid grid-cols-2 gap-4">
            <Stat label="Quizzes played" value={history.length} />
            <Stat label="Average accuracy" value={`${averageAccuracy}%`} />
          </div>

          <ul className="space-y-3">
            {history.map((session) => {
              const expanded = expandedId === session.session_id;
              return (
                <li key={session.id} className="overflow-hidden rounded-2xl border border-gray-100 bg-white shadow-sm">
                  <button
                    type="button"
                    aria-expanded={expanded}
                    onClick={() => onToggle(session.session_id)}
                    className="flex w-full items-center justify-between gap-4 p-5 text-left transition-colors hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-blue-500"
                  >
                    <div className="min-w-0">
                      <h3 className="truncate text-lg font-bold text-gray-800">{session.quiz_title}</h3>
                      <p className="mt-1 text-sm font-semibold text-gray-400">
                        {formatDate(session.played_at)} · {session.total_score} pts · {session.correct_answers}/{session.total_questions} correct
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-3">
                      <span className={`rounded-full px-3 py-1 text-sm font-bold ${accuracyClass(session.accuracy)}`}>{session.accuracy}%</span>
                      <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true" className={`h-5 w-5 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`}>
                        <path fillRule="evenodd" d="M5.23 7.21a.75.75 0 011.06.02L10 11.06l3.71-3.83a.75.75 0 111.08 1.04l-4.25 4.39a.75.75 0 01-1.08 0L5.21 8.27a.75.75 0 01.02-1.06z" clipRule="evenodd" />
                      </svg>
                    </div>
                  </button>

                  {expanded && (
                    <div className="space-y-4 border-t border-gray-100 bg-gray-50 p-4 sm:p-5">
                      {session.details.length === 0 ? (
                        <p className="text-center font-semibold text-gray-500">You didn't answer any questions in this game.</p>
                      ) : (
                        session.details.map((q, idx) => <AnswerReview key={idx} q={q} number={idx + 1} />)
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
