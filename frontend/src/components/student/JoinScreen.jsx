import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import { apiFetch } from '../../api';

const inputClass =
  'w-full rounded-xl bg-gray-100 p-4 text-lg font-semibold text-gray-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500';

function Tab({ active, onClick, children }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex-1 rounded-lg py-2.5 text-sm font-bold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 ${
        active ? 'bg-white text-gray-900 shadow-sm' : 'text-gray-500 hover:text-gray-700'
      }`}
    >
      {children}
    </button>
  );
}

function GuestJoinForm({ joinError, onJoin }) {
  const [roomCode, setRoomCode] = useState('');
  const [name, setName] = useState('');

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onJoin(roomCode.trim(), name.trim()); }}
      className="flex flex-col gap-3"
    >
      {joinError && <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{joinError}</p>}
      <label className="sr-only" htmlFor="room-pin">Room PIN</label>
      <input
        id="room-pin"
        type="text"
        required
        autoFocus
        autoComplete="off"
        autoCapitalize="characters"
        maxLength={6}
        placeholder="Room PIN"
        value={roomCode}
        onChange={(e) => setRoomCode(e.target.value.toUpperCase())}
        className={`${inputClass} text-center font-mono text-3xl font-black tracking-[0.3em] uppercase`}
      />
      <label className="sr-only" htmlFor="nickname">Nickname</label>
      <input
        id="nickname"
        type="text"
        required
        maxLength={20}
        autoComplete="off"
        placeholder="Nickname"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className={`${inputClass} text-center text-xl`}
      />
      <button type="submit" className="mt-1 min-h-12 rounded-xl bg-gray-900 py-4 text-lg font-bold text-white transition-colors hover:bg-gray-800 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2">
        Enter game
      </button>
    </form>
  );
}

function SignInForm({ onSignIn }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [isRegistering, setIsRegistering] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    setNotice('');
    try {
      if (isRegistering) {
        await apiFetch('/register', { method: 'POST', body: JSON.stringify({ email, password }) });
        setIsRegistering(false);
        setNotice('Account created. Sign in to continue.');
        return;
      }
      const data = await apiFetch('/token', {
        method: 'POST',
        body: new URLSearchParams({ username: email, password }),
      });
      onSignIn(data.access_token);
    } catch (err) {
      setError(err.message);
    }
  };

  const googleSignIn = async (credentialResponse) => {
    setError('');
    try {
      const data = await apiFetch('/google-login', {
        method: 'POST',
        body: JSON.stringify({ token: credentialResponse.credential }),
      });
      onSignIn(data.access_token);
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div>
      {error && <p role="alert" className="mb-3 rounded-xl bg-red-50 p-3 text-sm font-bold text-red-700">{error}</p>}
      {notice && <p role="status" className="mb-3 rounded-xl bg-green-50 p-3 text-sm font-bold text-green-700">{notice}</p>}
      <form onSubmit={submit} className="flex flex-col gap-3">
        <input type="email" required autoComplete="email" placeholder="Email (@csumb.edu)" value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
        <input type="password" required autoComplete={isRegistering ? 'new-password' : 'current-password'} placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
        <button type="submit" className="mt-1 min-h-12 rounded-xl bg-blue-600 py-4 text-lg font-bold text-white transition-colors hover:bg-blue-700 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2">
          {isRegistering ? 'Create account' : 'Sign in'}
        </button>
      </form>
      <div className="mt-4 text-center">
        <button
          type="button"
          onClick={() => { setIsRegistering(!isRegistering); setError(''); setNotice(''); }}
          className="text-sm font-bold text-blue-600 hover:underline focus:outline-none focus-visible:underline"
        >
          {isRegistering ? 'Already have an account? Sign in' : 'Need an account? Sign up'}
        </button>
      </div>
      <div className="mt-6 flex flex-col items-center border-t border-gray-100 pt-6">
        <GoogleLogin onSuccess={googleSignIn} onError={() => setError('Google sign-in failed.')} width="100%" />
      </div>
    </div>
  );
}

export default function JoinScreen({ professorEmail, joinError, onJoin, onSignIn, onSignOut }) {
  const [tab, setTab] = useState('guest');
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen w-full flex-col items-center bg-gray-100 px-4 py-10 sm:py-16">
      <div className="w-full max-w-md">
        <h1 className="mb-8 text-center text-4xl font-black tracking-tight text-gray-800 sm:text-5xl">CST 315 Quiz</h1>

        <div className="rounded-2xl bg-white p-5 shadow-sm sm:p-6">
          <div role="tablist" className="mb-6 flex gap-1 rounded-xl bg-gray-100 p-1">
            <Tab active={tab === 'guest'} onClick={() => setTab('guest')}>Play as guest</Tab>
            <Tab active={tab === 'account'} onClick={() => setTab('account')}>{professorEmail ? 'Account' : 'Sign in'}</Tab>
          </div>

          {tab === 'guest' && <GuestJoinForm joinError={joinError} onJoin={onJoin} />}

          {tab === 'account' && !professorEmail && <SignInForm onSignIn={onSignIn} />}

          {tab === 'account' && professorEmail && (
            <div className="text-center">
              <p className="mb-6 font-semibold text-gray-600">Signed in as <span className="font-bold text-gray-800">{professorEmail}</span></p>
              <button onClick={() => navigate('/host')} className="mb-3 min-h-12 w-full rounded-xl bg-blue-600 py-4 text-lg font-bold text-white transition-colors hover:bg-blue-700">
                Host dashboard
              </button>
              <button onClick={onSignOut} className="min-h-12 w-full rounded-xl border-2 border-gray-200 py-3 font-bold text-gray-600 transition-colors hover:bg-gray-50">
                Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
