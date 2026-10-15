import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';

interface Props {
  onClose: () => void;
  initialError?: string;
}

export default function AuthModal({ onClose, initialError }: Props) {
  const { signin, signup } = useAuth();
  const [tab, setTab] = useState<'signin' | 'signup'>('signin');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(initialError || '');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (initialError) {
      setError(initialError);
    }
  }, [initialError]);

  const handleTabChange = (nextTab: 'signin' | 'signup') => {
    setTab(nextTab);
    setError('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      if (tab === 'signin') {
        await signin(email, password);
      } else {
        await signup(email, password, name || undefined);
      }
      onClose();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Something went wrong';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleGoogle = () => {
    import('../api/client').then(({ api }) => api.googleLogin());
  };

  return (
    <div className="modal-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="modal" style={{ position: 'relative' }}>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          style={{
            position: 'absolute',
            top: 14,
            right: 14,
            background: 'none',
            border: 'none',
            color: 'var(--text-muted, #888)',
            fontSize: 22,
            lineHeight: 1,
            cursor: 'pointer',
            padding: '4px 8px',
          }}
        >
          ×
        </button>

        {/* Logo */}
        <div className="modal-logo">
          <div className="modal-logo-icon">G</div>
          <span className="modal-logo-name">GraphMind</span>
        </div>

        <h2>{tab === 'signin' ? 'Welcome back' : 'Create account'}</h2>
        <p>{tab === 'signin' ? 'Sign in to access your conversations' : 'Join GraphMind to save your chats'}</p>

        {/* Tabs */}
        <div className="modal-tabs">
          <button
            className={`modal-tab ${tab === 'signin' ? 'active' : ''}`}
            onClick={() => handleTabChange('signin')}
            type="button"
          >
            Sign In
          </button>
          <button
            className={`modal-tab ${tab === 'signup' ? 'active' : ''}`}
            onClick={() => handleTabChange('signup')}
            type="button"
          >
            Sign Up
          </button>
        </div>

        {/* Google OAuth */}
        <button className="btn-google" onClick={handleGoogle} type="button">
          <svg className="google-icon" viewBox="0 0 24 24">
            <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
            <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
            <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
            <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
          </svg>
          Continue with Google
        </button>

        <div className="divider">or</div>

        {/* Form */}
        <form onSubmit={handleSubmit}>
          {tab === 'signup' && (
            <div className="form-group">
              <label className="form-label">Name (optional)</label>
              <input
                className="form-input"
                type="text"
                placeholder="Your name"
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>
          )}
          <div className="form-group">
            <label className="form-label">Email</label>
            <input
              className="form-input"
              type="email"
              placeholder="you@example.com"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
            />
          </div>
          <div className="form-group">
            <label className="form-label">Password</label>
            <input
              className="form-input"
              type="password"
              placeholder="••••••••"
              required
              minLength={8}
              value={password}
              onChange={e => setPassword(e.target.value)}
            />
          </div>
          {error && (
            <div className="form-error" role="alert">
              <span className="form-error-icon">⚠</span>
              {error}
            </div>
          )}
          <button className="btn-primary" type="submit" disabled={loading}>
            {loading ? (
              <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                <span className="spinner" />
                Please wait…
              </span>
            ) : (
              tab === 'signin' ? 'Sign In' : 'Create Account'
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
