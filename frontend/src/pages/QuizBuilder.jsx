import { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { apiFetch, readToken } from '../api';
import { ANSWERS } from '../answers';
import AnswerShape from '../components/AnswerShape';

const QUESTION_FIELDS = ['text', 'option_red', 'option_blue', 'option_yellow', 'option_green', 'correct_option', 'time_limit_seconds', 'explanation'];

// `key` only identifies the card in React; it is stripped before saving
const emptyQuestion = () => ({
  key: crypto.randomUUID(),
  text: '', option_red: '', option_blue: '', option_yellow: '', option_green: '',
  correct_option: 'red', time_limit_seconds: 15, explanation: '',
});

export default function QuizBuilder() {
  const { quizId } = useParams();
  const [title, setTitle] = useState('');
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
    return <div className="flex h-screen items-center justify-center text-2xl font-bold text-gray-500">Loading quiz...</div>;
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8 pb-32">
      <div className="mx-auto max-w-4xl">

        {/* Header Section */}
        <div className="mb-8 flex items-center justify-between border-b border-gray-200 pb-6">
          <h1 className="text-4xl font-black text-gray-800">{quizId ? 'Edit Quiz' : 'Quiz Builder'}</h1>
          <button onClick={() => navigate('/host')} className="rounded-lg border-2 border-gray-300 px-6 py-2 font-bold text-gray-700 hover:bg-gray-100">
            Cancel
          </button>
        </div>

        {error && (
          <div role="alert" className="mb-8 flex flex-wrap items-center justify-between gap-4 rounded-xl bg-red-50 p-4 font-bold text-red-700">
            <span>{error}</span>
            {offerCopy && (
              <button onClick={() => saveQuiz(true)} disabled={isSaving} className="rounded-lg bg-red-600 px-4 py-2 text-white hover:bg-red-700 disabled:opacity-50">
                Save as a new quiz
              </button>
            )}
          </div>
        )}

        {/* Title Input */}
        <div className="mb-10 rounded-2xl bg-white p-8 shadow-sm border border-gray-100">
          <label htmlFor="quiz-title" className="mb-2 block text-sm font-bold text-gray-400 uppercase tracking-wider">Quiz Title</label>
          <input
            id="quiz-title"
            type="text"
            placeholder="e.g. CST 315 Midterm Review"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            className="w-full rounded-xl border-2 border-gray-200 p-4 text-3xl font-bold focus:border-blue-500 focus:outline-none"
          />
        </div>

        {/* Questions List */}
        <div className="space-y-12">
          {questions.map((q, idx) => (
            <div key={q.key} className="relative rounded-2xl bg-white p-8 shadow-sm border border-gray-100">

              <div className="mb-6 flex items-center justify-between">
                <h2 className="text-2xl font-bold text-gray-800">Question {idx + 1}</h2>
                {questions.length > 1 && (
                  <button onClick={() => removeQuestion(idx)} className="text-red-500 hover:underline font-bold">
                    Remove Question
                  </button>
                )}
              </div>

              {/* Question Text */}
              <input
                type="text"
                aria-label={`Question ${idx + 1} text`}
                placeholder="Type your question here..."
                value={q.text}
                onChange={(e) => updateQuestion(idx, 'text', e.target.value)}
                className="mb-8 w-full rounded-xl border-2 border-gray-200 p-4 text-xl font-semibold focus:border-blue-500 focus:outline-none"
              />

              {/* Grid for Options */}
              <div className="grid grid-cols-1 gap-4 mb-3 sm:grid-cols-2">
                {ANSWERS.map(({ color, bg }) => (
                  <label key={color} className={`flex items-center gap-3 rounded-xl border-2 bg-white p-2 pl-4 ${q.correct_option === color ? 'border-gray-900' : 'border-gray-200'}`}>
                    <span style={{ color: bg }}><AnswerShape color={color} className="h-6 w-6" /></span>
                    <input
                      type="text"
                      placeholder={`${color.charAt(0).toUpperCase() + color.slice(1)} answer`}
                      value={q[`option_${color}`]}
                      onChange={(e) => updateQuestion(idx, `option_${color}`, e.target.value)}
                      className="w-full bg-transparent p-2 text-lg font-bold text-gray-900 placeholder-gray-400 focus:outline-none"
                    />
                    {/* Radio Button to select Correct Answer */}
                    <input
                      type="radio"
                      name={`correct_${q.key}`}
                      aria-label={`${color} is correct`}
                      checked={q.correct_option === color}
                      onChange={() => updateQuestion(idx, 'correct_option', color)}
                      className="mr-2 h-5 w-5 shrink-0 cursor-pointer accent-gray-900"
                    />
                  </label>
                ))}
              </div>
              <p className="mb-6 text-sm font-bold text-gray-500">
                Select the radio button next to the correct answer.
              </p>

              {/* Explanation shown to students when they review the quiz */}
              <label className="mb-6 block">
                <span className="mb-2 block font-bold text-gray-600">Explanation <span className="font-semibold text-gray-400">(optional, shown after the question and in student review)</span></span>
                <textarea
                  rows={2}
                  value={q.explanation}
                  onChange={(e) => updateQuestion(idx, 'explanation', e.target.value)}
                  className="w-full rounded-xl border-2 border-gray-200 p-3 font-semibold focus:border-blue-500 focus:outline-none"
                />
              </label>

              {/* Timer Setting */}
              <div className="flex items-center space-x-4 border-t border-gray-100 pt-6">
                <label htmlFor={`time_${q.key}`} className="font-bold text-gray-600">Time Limit (Seconds):</label>
                <select
                  id={`time_${q.key}`}
                  value={q.time_limit_seconds}
                  onChange={(e) => updateQuestion(idx, 'time_limit_seconds', parseInt(e.target.value))}
                  className="rounded-lg border-2 border-gray-200 p-2 font-bold focus:outline-none"
                >
                  {[10, 15, 20, 30, 60, 90, 120].map((s) => <option key={s} value={s}>{s}</option>)}
                </select>
              </div>

            </div>
          ))}
        </div>

        {/* Floating Action Bar */}
        <div className="fixed bottom-0 left-0 right-0 flex justify-center space-x-6 bg-white border-t border-gray-200 p-6 shadow-2xl">
          <button onClick={addQuestion} className="rounded-xl bg-gray-200 px-8 py-4 text-xl font-bold text-gray-800 hover:bg-gray-300">
            + Add Another Question
          </button>
          <button onClick={() => saveQuiz()} disabled={isSaving} className="rounded-xl bg-blue-600 px-12 py-4 text-xl font-bold text-white shadow-lg hover:bg-blue-700 disabled:opacity-50">
            {isSaving ? 'Saving...' : quizId ? 'Save Changes' : 'Save & Publish Quiz'}
          </button>
        </div>

      </div>
    </div>
  );
}
