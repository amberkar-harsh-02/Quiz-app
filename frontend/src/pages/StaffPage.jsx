import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch, readToken } from '../api';
import { Alert, Button, Field, Panel, Wordmark, inputClass } from '../components/ui';

const dateFormat = new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
// The server stores naive UTC timestamps
const formatDate = (iso) => (iso ? dateFormat.format(new Date(`${iso}Z`)) : '');

// Admins only: who else can host games, edit quizzes and see analytics
export default function StaffPage() {
  const [admins, setAdmins] = useState([]);
  const [staff, setStaff] = useState([]);
  const [email, setEmail] = useState('');
  const [message, setMessage] = useState(null); // { type: 'error' | 'success', text }
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const loadStaff = useCallback(() => apiFetch('/staff').then((data) => {
    setAdmins(data.admins);
    setStaff(data.staff);
  }), []);

  useEffect(() => {
    if (!readToken()) { navigate('/'); return; }
    apiFetch('/me')
      .then((me) => {
        if (!me.is_admin) { navigate('/host'); return; }
        return loadStaff();
      })
      .catch((err) => setMessage({ type: 'error', text: `Couldn't load the staff list: ${err.message}` }))
      .finally(() => setLoading(false));
  }, [navigate, loadStaff]);

  const addStaff = async (e) => {
    e.preventDefault();
    setMessage(null);
    try {
      const added = await apiFetch('/staff', { method: 'POST', body: JSON.stringify({ email }) });
      setEmail('');
      setMessage({
        type: 'success',
        text: added.signed_up
          ? `${added.email} can host games now.`
          : `${added.email} will be able to host games once they sign up.`,
      });
      await loadStaff();
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    }
  };

  const removeStaff = async (staffEmail) => {
    if (!window.confirm(`Remove ${staffEmail}? They won't be able to host games or edit quizzes any more. Their quizzes are kept.`)) return;
    setMessage(null);
    try {
      await apiFetch(`/staff/${encodeURIComponent(staffEmail)}`, { method: 'DELETE' });
      setMessage({ type: 'success', text: `Removed ${staffEmail}.` });
      await loadStaff();
    } catch (err) {
      setMessage({ type: 'error', text: err.message });
    }
  };

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-xl text-muted">Loading staff...</div>;
  }

  return (
    <div className="min-h-screen">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-4xl items-center justify-between gap-4 px-6 py-3">
          <Wordmark title="Quiz App" />
          <Button variant="secondary" size="sm" onClick={() => navigate('/host')}>Back to My Quizzes</Button>
        </div>
      </header>

      <main className="mx-auto max-w-4xl px-6 py-8">
        <h1 className="mb-1 text-3xl font-bold tracking-tight">Staff</h1>
        <p className="mb-6 text-muted">Professors and TAs on this list can host games, edit quizzes and see analytics. Everyone else signs in as a student.</p>

        {message && (
          <div className="mb-6">
            <Alert tone={message.type} onDismiss={() => setMessage(null)}>{message.text}</Alert>
          </div>
        )}

        <Panel className="mb-8 p-5">
          <form onSubmit={addStaff} className="flex flex-col gap-3 sm:flex-row sm:items-end">
            <Field label="Add a professor or TA" hint="(they don't need an account yet)" id="staff-email" className="flex-grow">
              <input
                id="staff-email"
                type="email"
                required
                placeholder="name@csumb.edu"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={inputClass}
              />
            </Field>
            <Button type="submit" className="sm:w-28">Add</Button>
          </form>
        </Panel>

        <section className="mb-8">
          <h2 className="mb-3 text-xl font-bold">Staff</h2>
          {staff.length === 0 ? (
            <Panel className="p-8 text-center text-muted">No one yet. Add an email above to give someone access.</Panel>
          ) : (
            <Panel className="overflow-hidden">
              <table className="w-full text-left">
                <thead className="border-b border-line bg-paper text-sm text-muted">
                  <tr>
                    <th scope="col" className="px-5 py-3 font-bold">Email</th>
                    <th scope="col" className="px-5 py-3 font-bold">Account</th>
                    <th scope="col" className="hidden px-5 py-3 font-bold sm:table-cell">Added</th>
                    <th scope="col" className="px-5 py-3"><span className="sr-only">Remove</span></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {staff.map((s) => (
                    <tr key={s.email}>
                      <td className="px-5 py-3 font-bold">{s.email}</td>
                      <td className={`px-5 py-3 ${s.signed_up ? 'text-ok' : 'text-muted'}`}>{s.signed_up ? 'Signed up' : 'Not signed up yet'}</td>
                      <td className="hidden px-5 py-3 text-sm text-muted sm:table-cell">
                        {formatDate(s.added_at)}{s.added_by && s.added_by !== '(carried over)' ? ` by ${s.added_by}` : ''}
                      </td>
                      <td className="px-5 py-3 text-right">
                        <Button variant="ghost" size="sm" onClick={() => removeStaff(s.email)} className="hover:!bg-bad-soft hover:!text-bad">Remove</Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Panel>
          )}
        </section>

        <section>
          <h2 className="mb-1 text-xl font-bold">Admins</h2>
          <p className="mb-3 text-sm text-muted">Admins can also manage this list. They're set in the server's <code className="font-mono">ADMIN_EMAILS</code> setting.</p>
          <Panel as="ul" className="divide-y divide-line">
            {admins.map((a) => <li key={a} className="px-5 py-3 font-bold">{a}</li>)}
          </Panel>
        </section>
      </main>
    </div>
  );
}
