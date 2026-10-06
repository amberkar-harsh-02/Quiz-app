import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiFetch, readToken } from '../api';
import { ANSWERS } from '../answers';
import AnswerKey from '../components/AnswerKey';
import { Alert, Button, Field, Panel, Wordmark, inputClass } from '../components/ui';

const QUESTION_FIELDS = ['text', 'option_red', 'option_blue', 'option_yellow', 'option_green', 'correct_option', 'time_limit_seconds', 'explanation'];

// `key` only identifies the card in React; it is stripped before saving
const emptyQuestion = () => ({
  key: crypto.randomUUID(),
  text: '', option_red: '', option_blue: '', option_yellow: '', option_green: '',
  correct_option: 'red', time_limit_seconds: 15, explanation: '',
});

function SwitchRow({ id, label, checked, onChange, children }) {
  return (
    <div className="flex items-start gap-4 p-4">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-labelledby={`${id}-label`}
        onClick={() => onChange(!checked)}
        className={`relative mt-0.5 h-6 w-11 shrink-0 rounded-full transition-colors ${checked ? 'bg-brand' : 'bg-line'}`}
      >
        <span className={`absolute left-0.5 top-0.5 h-5 w-5 rounded-full bg-white shadow transition-transform motion-reduce:transition-none ${checked ? 'translate-x-5' : ''}`} />
      </button>
      <div>
        <p id={`${id}-label`} className="font-bold">{label}</p>
        <p className="text-sm text-muted">{children}</p>
      </div>
    </div>
  );
}

export default function QuizBuilder() {
  const { quizId } = useParams();
  const [title, setTitle] = useState('');
  // Off: no question is timed and the professor moves the game along
  const [useTimer, setUseTimer] = useState(true);
  // Off: after every question the results wait for the professor's "Next Question"
  const [autoAdvance, setAutoAdvance] = useState(true);
  const [questions, setQuestions] = useState(() => [emptyQuestion()]);
  const [isLoading, setIsLoading] = useState(Boolean(quizId));
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  // Set when the server refuses to change a quiz that has already been played
  const [offerCopy, setOfferCopy] = useState(false);

  const navigate = useNavigate();

  useEffect(() => {
    if (!readToken()) { navigate('/'); return; }
    if (!quizId) return;

    apiFetch(`/quizzes/${quizId}`)
      .then((quiz) => {
        setTitle(quiz.title);
        setUseTimer(quiz.use_timer ?? true);
        setAutoAdvance(quiz.auto_advance_results ?? true);
        setQuestions(quiz.questions.map((q) => ({ ...q, key: crypto.randomUUID(), explanation: q.explanation ?? '' })));
      })
      .catch((err) => setError(`Couldn't load this quiz: ${err.message}`))
      .finally(() => setIsLoading(false));
  }, [quizId, navigate]);

  const addQuestion = () => {
    setQuestions([...questions, emptyQuestion()]);
  };

  const removeQuestion = (index) => {
    setQuestions(questions.filter((_, i) => i !== index));
  };

  const updateQuestion = (index, field, value) => {
    setQuestions(questions.map((q, i) => (i === index ? { ...q, [field]: value } : q)));
  };

  // The error banner sits at the top, but Save is in the bar at the bottom
  const fail = (message) => {
    setError(message);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const saveQuiz = async (asNewQuiz = false) => {
    setError('');
    setOfferCopy(false);
    if (!title.trim()) return fail('Please enter a quiz title.');

    // Quick validation to ensure no empty fields
    const incomplete = questions.findIndex((q) => ['text', ...ANSWERS.map((a) => `option_${a.color}`)].some((f) => !q[f].trim()));
    if (incomplete !== -1) return fail(`Please fill in the question and all four answers for question ${incomplete + 1}.`);

    const payload = {
      title,
      use_timer: useTimer,
      auto_advance_results: autoAdvance,
      questions: questions.map((q) => Object.fromEntries(QUESTION_FIELDS.map((f) => [f, q[f]]))),
    };
    const editing = quizId && !asNewQuiz;

    setIsSaving(true);
    try {
      await apiFetch(editing ? `/quizzes/${quizId}` : '/quizzes/builder', {
        method: editing ? 'PUT' : 'POST',
        body: JSON.stringify(payload),
      });
      navigate('/host');
    } catch (err) {
      fail(err.message);
      setOfferCopy(editing && err.message.includes('Duplicate'));
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return <div className="flex h-screen items-center justify-center text-xl text-muted">Loading quiz...</div>;
  }

  return (
    <div className="min-h-screen pb-28">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-6 py-3">
          <Wordmark title="Quiz App" />
          <Button variant="secondary" size="sm" onClick={() => navigate('/host')}>Cancel</Button>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="mb-6 text-3xl font-bold tracking-tight">{quizId ? 'Edit Quiz' : 'Quiz Builder'}</h1>

        {error && (
          <div className="mb-6">
            <Alert
              action={offerCopy && (
                <Button variant="danger" size="sm" onClick={() => saveQuiz(true)} disabled={isSaving}>Save as a new quiz</Button>
              )}
            >
              {error}
            </Alert>
          </div>
        )}

        <Field label="Quiz Title" id="quiz-title" className="mb-8">
          <input
            id="quiz-title"
            type="text"
            placeholder="e.g. CST 315 Midterm Review"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className={`${inputClass} text-2xl font-bold`}
          />
        </Field>

        <Panel className="mb-8 divide-y divide-line">
          <SwitchRow id="use-timer" label="Use a timer" checked={useTimer} onChange={setUseTimer}>
            {useTimer
              ? 'Each question closes when its time runs out. Pick "No timer" on a question to run just that one yourself.'
              : 'No timers in this quiz. Questions stay open until everyone answers or you show the results.'}
          </SwitchRow>
          <SwitchRow id="auto-advance" label="Move on from results automatically" checked={autoAdvance} onChange={setAutoAdvance}>
            {autoAdvance
              ? 'After a timed question, results show for 5–10 seconds, then the next question starts. Questions with no timer always wait for you.'
              : 'Results stay up after every question until you click Next Question.'}
          </SwitchRow>
        </Panel>

        <ol className="space-y-6">
          {questions.map((q, idx) => (
            <Panel as="li" key={q.key} className="p-6">
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-lg font-bold">Question {idx + 1}</h2>
                {questions.length > 1 && (
                  <Button variant="ghost" size="sm" onClick={() => removeQuestion(idx)} className="hover:!bg-bad-soft hover:!text-bad">
                    Remove Question
                  </Button>
                )}
              </div>

              <input
                type="text"
                aria-label={`Question ${idx + 1} text`}
                placeholder="Type your question here..."
                value={q.text}
                onChange={(e) => updateQuestion(idx, 'text', e.target.value)}
                className={`${inputClass} mb-5 text-lg font-bold`}
              />

              <fieldset className="mb-5">
                <legend className="mb-2 text-sm text-muted">Answers. Pick the correct one with the radio button.</legend>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {ANSWERS.map(({ color, letter }) => {
                    const isCorrect = q.correct_option === color;
                    return (
                      <label
                        key={color}
                        className={`flex items-center gap-3 rounded-chip border bg-white py-1 pl-3 pr-3 transition-colors ${isCorrect ? 'border-ok bg-ok-soft' : 'border-line hover:border-muted'}`}
                      >
                        <AnswerKey color={color} />
                        <input
                          type="text"
                          placeholder={`Answer ${letter}`}
                          value={q[`option_${color}`]}
                          onChange={(e) => updateQuestion(idx, `option_${color}`, e.target.value)}
                          className="w-full rounded-chip bg-transparent px-1 py-2 font-bold placeholder:font-normal placeholder:text-muted/70 focus-visible:ring-offset-0"
                        />
                        <input
                          type="radio"
                          name={`correct_${q.key}`}
                          aria-label={`${letter} is correct`}
                          checked={isCorrect}
                          onChange={() => updateQuestion(idx, 'correct_option', color)}
                          className="h-5 w-5 shrink-0 cursor-pointer accent-[#1E7A3E]"
                        />
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <Field label="Explanation" hint="(optional, shown after the question and in student review)" id={`explanation_${q.key}`} className="mb-5">
                <textarea
                  id={`explanation_${q.key}`}
                  rows={2}
                  value={q.explanation}
                  onChange={(e) => updateQuestion(idx, 'explanation', e.target.value)}
                  className={inputClass}
                />
              </Field>

              <div className="flex items-center gap-3 border-t border-line pt-4">
                <label htmlFor={`time_${q.key}`} className="text-sm font-bold">Time limit</label>
                <select
                  id={`time_${q.key}`}
                  value={useTimer ? (q.time_limit_seconds ?? '') : ''}
                  disabled={!useTimer}
                  onChange={(e) => updateQuestion(idx, 'time_limit_seconds', e.target.value === '' ? null : parseInt(e.target.value))}
                  className="rounded-chip border border-line bg-white px-3 py-1.5 font-bold hover:border-muted disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <option value="">No timer</option>
                  {[10, 15, 20, 30, 60, 90, 120].map((s) => <option key={s} value={s}>{s} seconds</option>)}
                </select>
                {!useTimer && <span className="text-sm text-muted">Timer is off for this quiz</span>}
              </div>
            </Panel>
          ))}
        </ol>
      </main>

      {/* Sticky action bar */}
      <div className="fixed inset-x-0 bottom-0 border-t border-line bg-white/95 shadow-[0_-8px_24px_rgba(23,32,51,0.08)] backdrop-blur">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-6 py-4">
          <span className="text-sm text-muted">{questions.length} {questions.length === 1 ? 'question' : 'questions'}</span>
          <div className="flex gap-3">
            <Button variant="secondary" onClick={addQuestion}>+ Add Another Question</Button>
            <Button onClick={() => saveQuiz()} disabled={isSaving}>
              {isSaving ? 'Saving...' : quizId ? 'Save Changes' : 'Save & Publish Quiz'}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
