import { useState, useEffect, useRef, useCallback } from 'react';
import { useAuth } from './contexts/AuthContext';
import { api } from './api/client';
import type { Conversation, Message } from './api/client';
import Sidebar from './components/Sidebar';
import WelcomeScreen from './components/WelcomeScreen';
import MessageList from './components/MessageList';
import MessageInput from './components/MessageInput';
import AuthModal from './components/AuthModal';

// ── Icons ────────────────────────────────────────────────────────────────────
const IconSearch = () => (
  <svg width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
    <circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35" strokeLinecap="round"/>
  </svg>
);

const IconMenu = () => (
  <svg width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" viewBox="0 0 24 24">
    <path d="M3 12h18M3 6h18M3 18h18" strokeLinecap="round"/>
  </svg>
);

function genId() {
  return Math.random().toString(36).slice(2);
}

export default function App() {
  const { user, isLoading, setTokenFromCallback } = useAuth();

  // ── State ────────────────────────────────────────────────────────────────
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [isThinking, setIsThinking] = useState(false);
  const [showAuth, setShowAuth] = useState(false);
  const [authError, setAuthError] = useState('');
  const [inputValue, setInputValue] = useState('');
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState(false);

  const bottomRef = useRef<HTMLDivElement>(null);

  // ── Handle Google OAuth redirect: picks up #token=... or ?auth_error=... ────
  useEffect(() => {
    // Success: backend set #token=<jwt> on the redirect
    const hash = window.location.hash;
    if (hash.startsWith('#token=')) {
      const token = hash.slice('#token='.length);
      if (token) {
        setTokenFromCallback(token)
          .then(() => {
            setShowAuth(false);
            setAuthError('');
          })
          .catch((err) => {
            console.error(err);
            setAuthError(err instanceof Error ? err.message : 'Authentication failed');
            setShowAuth(true);
          });
        window.history.replaceState(null, '', '/');
      }
      return;
    }
    // Failure: backend set ?auth_error=<message> on the redirect
    const params = new URLSearchParams(window.location.search);
    const err = params.get('auth_error');
    if (err) {
      setAuthError(decodeURIComponent(err));
      setShowAuth(true);
      window.history.replaceState(null, '', '/');
    }
  }, [setTokenFromCallback]);

  // ── Load conversation list when user changes ──────────────────────────────
  useEffect(() => {
    if (user) {
      api.listConversations().then(setConversations).catch(console.error);
    } else {
      setConversations([]);
      setActiveConvId(null);
      setMessages([]);
    }
  }, [user]);

  // ── Load messages when active conversation changes ───────────────────────
  useEffect(() => {
    if (!activeConvId || activeConvId === 'guest') return;
    api.getConversation(activeConvId)
      .then(detail => setMessages(detail.messages))
      .catch(console.error);
  }, [activeConvId]);

  // ── Auto-scroll to bottom ─────────────────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  // ── Handle new conversation ───────────────────────────────────────────────
  const handleNew = useCallback(() => {
    setActiveConvId(null);
    setMessages([]);
  }, []);

  // ── Handle conversation select ────────────────────────────────────────────
  const handleSelect = useCallback((id: string) => {
    setActiveConvId(id);
  }, []);

  // ── Handle delete ─────────────────────────────────────────────────────────
  const handleDelete = useCallback(async (id: string) => {
    try {
      await api.deleteConversation(id);
      setConversations(prev => prev.filter(c => c.id !== id));
      if (activeConvId === id) {
        setActiveConvId(null);
        setMessages([]);
      }
    } catch (e) {
      console.error(e);
    }
  }, [activeConvId]);

  // ── Handle send ──────────────────────────────────────────────────────────
  const handleSend = useCallback(async (text: string) => {
    // Optimistic user message
    const optimisticId = genId();
    const userMsg: Message = {
      id: optimisticId,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setIsThinking(true);

    try {
      const res = await api.chat(text, activeConvId ?? undefined);

      // For authenticated users: update conversation list + set active
      if (user) {
        setActiveConvId(res.conversation_id);
        // Refresh conversation list (to get updated title/timestamp)
        const updatedList = await api.listConversations();
        setConversations(updatedList);
        // Append assistant reply
        const assistantMsg: Message = {
          id: genId(),
          role: 'assistant',
          content: res.answer,
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, assistantMsg]);
      } else {
        // Guest: just show the response
        setActiveConvId('guest');
        const assistantMsg: Message = {
          id: genId(),
          role: 'assistant',
          content: res.answer,
          created_at: new Date().toISOString(),
        };
        setMessages(prev => [...prev, assistantMsg]);
      }
    } catch (err: unknown) {
      const errMsg: Message = {
        id: genId(),
        role: 'assistant',
        content: err instanceof Error ? `Error: ${err.message}` : 'Something went wrong. Please try again.',
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setIsThinking(false);
    }
  }, [activeConvId, user]);

  // ── Handle regenerate ──────────────────────────────────────────────────────
  const handleRegenerate = useCallback(async (msgId: string) => {
    const idx = messages.findIndex(m => m.id === msgId);
    if (idx <= 0) return;
    
    // Find previous user message
    let text = '';
    for (let i = idx - 1; i >= 0; i--) {
      if (messages[i].role === 'user') {
        text = messages[i].content;
        break;
      }
    }
    if (!text) return;

    // Remove the message we're regenerating
    setMessages(prev => prev.slice(0, idx));
    setIsThinking(true);

    try {
      const res = await api.chat(text, activeConvId ?? undefined);
      const assistantMsg: Message = {
        id: genId(),
        role: 'assistant',
        content: res.answer,
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: unknown) {
      const errMsg: Message = {
        id: genId(),
        role: 'assistant',
        content: err instanceof Error ? `Error: ${err.message}` : 'Something went wrong. Please try again.',
        created_at: new Date().toISOString(),
      };
      setMessages(prev => [...prev, errMsg]);
    } finally {
      setIsThinking(false);
    }
  }, [messages, activeConvId]);

  // ── Loading ───────────────────────────────────────────────────────────────
  if (isLoading) {
    return (
      <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
        <div className="thinking-dots">
          <div className="thinking-dot" />
          <div className="thinking-dot" />
          <div className="thinking-dot" />
        </div>
      </div>
    );
  }

  const initials = user?.name
    ? user.name.split(' ').map(n => n[0]).join('').slice(0, 2).toUpperCase()
    : user?.email?.[0].toUpperCase() ?? '?';

  return (
    <div className="app-layout">
      {isMobileSidebarOpen && (
        <div className="sidebar-overlay" onClick={() => setIsMobileSidebarOpen(false)} />
      )}
      <Sidebar
        conversations={conversations}
        activeId={activeConvId}
        onSelect={(id) => { handleSelect(id); setIsMobileSidebarOpen(false); }}
        onNew={() => { handleNew(); setIsMobileSidebarOpen(false); }}
        onDelete={handleDelete}
        onSignIn={() => { setAuthError(''); setShowAuth(true); }}
        isMobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
      />

      <div className="main-area">
        {/* Top bar */}
        <div className="topbar">
          <div className="topbar-left">
            <button className="icon-btn mobile-menu-btn" onClick={() => setIsMobileSidebarOpen(true)} aria-label="Open sidebar">
              <IconMenu />
            </button>
            <div className="model-badge">
              <div className="model-dot" />
              GraphMind AI
            </div>
          </div>
          <div className="topbar-right">
            <button className="icon-btn" title="Search" aria-label="Search"><IconSearch /></button>
            {user ? (
              <div className="topbar-avatar" title={user.email}>{initials}</div>
            ) : (
              <button
                className="icon-btn"
                style={{ padding: '0 12px', width: 'auto', fontSize: 12, color: 'var(--accent)' }}
                onClick={() => { setAuthError(''); setShowAuth(true); }}
              >
                Sign In
              </button>
            )}
          </div>
        </div>

        {/* Status strip */}
        <div className="status-strip">
          <div className="status-left">
            <div className="status-item">
              <div className="status-dot" />
              RAG INDEX: SYNCHRONIZED
            </div>
            <span className="status-sep">•</span>
            <div className="status-item">4,985 WIKI CHUNKS</div>
          </div>
          <div className="status-right">
            <a href="https://wiki.metakgp.org" target="_blank" rel="noreferrer" style={{ color: 'var(--accent)' }}>
              wiki.metakgp.org
            </a>
            <span className="status-sep">•</span>
            <div className="status-item">MODEL: gemini-3.5-flash ● ACTIVE</div>
          </div>
        </div>

        {/* Chat viewport */}
        <div className="chat-viewport">
          <div className="chat-inner">
            {messages.length === 0 && !isThinking ? (
              <WelcomeScreen onSuggest={(text) => setInputValue(text)} />
            ) : (
              <MessageList messages={messages} isThinking={isThinking} onRegenerate={handleRegenerate} />
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* Input */}
        <MessageInput 
          value={inputValue}
          onChange={setInputValue}
          onSend={handleSend} 
          disabled={isThinking} 
        />
      </div>

      {/* Auth modal */}
      {showAuth && (
        <AuthModal
          onClose={() => {
            setShowAuth(false);
            setAuthError('');
          }}
          initialError={authError}
        />
      )}
    </div>
  );
}
