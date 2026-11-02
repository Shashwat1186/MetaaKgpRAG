function getBaseUrl(): string {
  // If explicitly configured in VITE_API_URL, use it (strip any trailing slashes)
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl && typeof envUrl === 'string' && envUrl.trim()) {
    return envUrl.trim().replace(/\/+$/, '');
  }

  // Browser-based intelligent fallback
  if (typeof window !== 'undefined') {
    const hostname = window.location.hostname;
    // Local development
    if (hostname === 'localhost' || hostname === '127.0.0.1') {
      return window.location.port === '8000' ? '' : 'http://localhost:8000';
    }
    // If hosted directly on Render (same domain as backend)
    if (hostname.endsWith('onrender.com')) {
      return '';
    }
  }

  // Production fallback for Vercel/external domains when VITE_API_URL is unset
  return 'https://metaakgprag.onrender.com';
}

const BASE_URL = getBaseUrl();

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

  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  const targetUrl = `${BASE_URL}${cleanPath}`;

  let res: Response;
  try {
    res = await fetch(targetUrl, { ...options, headers });
  } catch (networkErr) {
    // fetch() itself threw — server is unreachable or CORS preflight rejected
    throw new Error(
      `Cannot reach the backend server at ${targetUrl}. Please ensure the backend is running and CORS is configured.`
    );
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    // FastAPI validation errors come as { detail: [{msg, loc, type}] }
    let message: string;
    if (Array.isArray(body?.detail)) {
      message = body.detail.map((d: { msg: string }) => d.msg).join(', ');
    } else if (body?.detail) {
      message = body.detail;
    } else if (res.status === 404) {
      message = `Backend endpoint not found (404) at ${targetUrl}. Please check VITE_API_URL in your frontend deployment settings.`;
    } else {
      message = `Request failed with status ${res.status}`;
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
