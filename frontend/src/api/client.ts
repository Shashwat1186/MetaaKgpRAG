const BASE_URL = import.meta.env.VITE_API_URL || (typeof window !== 'undefined' && window.location.hostname === '127.0.0.1' ? 'http://127.0.0.1:8000' : 'http://localhost:8000');

function getToken(): string | null {
  return localStorage.getItem('gm_token');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
  } catch (networkErr) {
    // fetch() itself threw — server is unreachable
    throw new Error(
      'Cannot reach the server. Make sure the backend is running on ' + BASE_URL
    );
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    // FastAPI validation errors come as { detail: [{msg, loc, type}] }
    let message: string;
    if (Array.isArray(body.detail)) {
      message = body.detail.map((d: { msg: string }) => d.msg).join(', ');
    } else {
      message = body.detail || `Request failed (${res.status})`;
    }
    throw new Error(message);
  }

  if (res.status === 204) return undefined as T;
  return res.json();
}

// ── Auth ──────────────────────────────────────────────────────────────────────
export const api = {
  signup: (email: string, password: string, name?: string) =>
    request<{ access_token: string; user: User }>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password, name }),
    }),

  signin: (email: string, password: string) =>
    request<{ access_token: string; user: User }>('/auth/signin', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<User>('/auth/me'),

  googleLogin: () => {
    window.location.href = `${BASE_URL}/auth/google`;
  },

  // ── Conversations ───────────────────────────────────────────────────────────
  listConversations: () => request<Conversation[]>('/conversations'),

  createConversation: (title?: string) =>
    request<Conversation>('/conversations', {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),

  getConversation: (id: string) =>
    request<ConversationDetail>(`/conversations/${id}`),

  deleteConversation: (id: string) =>
    request<void>(`/conversations/${id}`, { method: 'DELETE' }),

  renameConversation: (id: string, title: string) =>
    request<Conversation>(`/conversations/${id}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),

  // ── Chat ───────────────────────────────────────────────────────────────────
  chat: (message: string, conversation_id?: string) =>
    request<{ answer: string; conversation_id: string }>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, conversation_id }),
    }),
};

// ── Types ──────────────────────────────────────────────────────────────────────
export interface User {
  id: string;
  email: string;
  name: string | null;
  provider: string | null;
  created_at: string;
}

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: Message[];
}
