import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { GoogleLogin } from '@react-oauth/google';
import { apiFetch } from '../../api';
import { Alert, Button, Field, Panel, Wordmark, inputClass, pinInputClass } from '../ui';

function Tab({ active, onClick, children }) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`relative flex-1 pb-3 text-base font-bold transition-colors ${
        active ? 'text-ink' : 'text-muted hover:text-ink'
      }`}
    >
      {children}
      <span className={`absolute inset-x-0 -bottom-px h-0.5 rounded-full transition-colors ${active ? 'bg-brand' : 'bg-transparent'}`} />
    </button>
  );
}

function GuestJoinForm({ joinError, onJoin }) {
  const [roomCode, setRoomCode] = useState('');
  const [name, setName] = useState('');

  return (
    <form
      onSubmit={(e) => { e.preventDefault(); onJoin(roomCode.trim(), name.trim()); }}
      className="flex flex-col gap-4"
    >
      {joinError && <Alert>{joinError}</Alert>}
      <Field label="Room PIN" hint="shown on the projector" id="room-pin">
        <input
          id="room-pin"
          type="text"
          required
          autoFocus
          autoComplete="off"
          autoCapitalize="characters"
          maxLength={6}
          placeholder="ABC123"
          value={roomCode}
          onChange={(e) => setRoomCode(e.target.value.toUpperCase())}
          className={pinInputClass}
        />
      </Field>
      <Field label="Nickname" id="nickname">
        <input
          id="nickname"
          type="text"
          required
          maxLength={20}
          autoComplete="off"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className={inputClass}
        />
      </Field>
      <Button type="submit" size="lg" className="mt-2 w-full">Enter game</Button>
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
    <div className="flex flex-col gap-4">
      {error && <Alert>{error}</Alert>}
      {notice && <Alert tone="success">{notice}</Alert>}
      <form onSubmit={submit} className="flex flex-col gap-4">
        <Field label="CSUMB email" id="email">
          <input id="email" type="email" required autoComplete="email" placeholder="you@csumb.edu" value={email} onChange={(e) => setEmail(e.target.value)} className={inputClass} />
        </Field>
        <Field label="Password" id="password">
          <input id="password" type="password" required autoComplete={isRegistering ? 'new-password' : 'current-password'} value={password} onChange={(e) => setPassword(e.target.value)} className={inputClass} />
        </Field>
        <Button type="submit" size="lg" className="mt-2 w-full">
          {isRegistering ? 'Create account' : 'Sign in'}
        </Button>
      </form>
      <button
        type="button"
        onClick={() => { setIsRegistering(!isRegistering); setError(''); setNotice(''); }}
        className="self-center rounded-chip px-2 py-1 text-sm font-bold text-brand hover:underline"
      >
        {isRegistering ? 'Already have an account? Sign in' : 'Need an account? Sign up'}
      </button>
      <div className="flex items-center gap-3 text-sm text-muted">
        <span className="h-px flex-grow bg-line" />or<span className="h-px flex-grow bg-line" />
      </div>
      <div className="flex justify-center">
        <GoogleLogin onSuccess={googleSignIn} onError={() => setError('Google sign-in failed.')} width="100%" />
      </div>
    </div>
  );
}

export default function JoinScreen({ professorEmail, joinError, onJoin, onSignIn, onSignOut }) {
  const [tab, setTab] = useState('guest');
  const navigate = useNavigate();

  return (
    <div className="flex min-h-screen w-full flex-col items-center px-4 py-10 sm:py-20">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex justify-center">
          <h1><Wordmark title="Quiz App" /></h1>
        </div>

        <Panel className="p-6">
          <div role="tablist" className="mb-6 flex gap-6 border-b border-line">
            <Tab active={tab === 'guest'} onClick={() => setTab('guest')}>Play as guest</Tab>
            <Tab active={tab === 'account'} onClick={() => setTab('account')}>{professorEmail ? 'Account' : 'Sign in'}</Tab>
          </div>

          {tab === 'guest' && <GuestJoinForm joinError={joinError} onJoin={onJoin} />}

          {tab === 'account' && !professorEmail && <SignInForm onSignIn={onSignIn} />}

          {tab === 'account' && professorEmail && (
            <div className="flex flex-col gap-3">
              <p className="mb-2 text-muted">Signed in as <span className="font-bold text-ink">{professorEmail}</span></p>
              <Button size="lg" className="w-full" onClick={() => navigate('/host')}>Host dashboard</Button>
              <Button variant="secondary" className="w-full" onClick={onSignOut}>Log out</Button>
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
