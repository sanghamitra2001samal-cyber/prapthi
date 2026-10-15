// Auth API client. The session lives in an httpOnly cookie set by the server,
// so there's no token to store in JS (safer against XSS) — every request just
// sends credentials.
const API_BASE = import.meta.env.VITE_API_BASE ?? '/api';

export interface AuthResult {
  ok: boolean;
  error?: string;
  message?: string;
  unverified?: boolean;
  user?: string;
  isAdmin?: boolean;
}

async function post(path: string, body: object): Promise<Response> {
  return fetch(`${API_BASE}${path}`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

async function parse(res: Response): Promise<AuthResult> {
  const data = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  if (res.ok) {
    return {
      ok: true,
      message: data.message as string | undefined,
      user: data.user as string | undefined,
      isAdmin: data.is_admin as boolean | undefined,
    };
  }
  if (res.status === 429)
    return { ok: false, error: 'Too many attempts. Please wait a few minutes.' };
  return {
    ok: false,
    error: (data.error as string) ?? 'Something went wrong.',
    unverified: data.error === 'unverified',
  };
}

export async function checkAuth(): Promise<{ user: string; isAdmin: boolean } | null> {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, {
      credentials: 'include',
      signal: AbortSignal.timeout(6000),
    });
    if (!res.ok) return null;
    const d = (await res.json()) as { user?: string; is_admin?: boolean };
    return d.user ? { user: d.user, isAdmin: !!d.is_admin } : null;
  } catch {
    return null;
  }
}

export const login = (email: string, password: string) =>
  post('/auth/login', { email, password }).then(parse);

export const signup = (email: string, password: string) =>
  post('/auth/signup', { email, password }).then(parse);

export const verifyEmail = (email: string, code: string) =>
  post('/auth/verify', { email, code }).then(parse);

export const resendCode = (email: string) =>
  post('/auth/resend', { email }).then(parse);

export const forgotPassword = (email: string) =>
  post('/auth/forgot', { email }).then(parse);

export const resetPassword = (email: string, code: string, password: string) =>
  post('/auth/reset', { email, code, password }).then(parse);

export async function logout(): Promise<void> {
  try {
    await post('/auth/logout', {});
  } catch {
    /* ignore */
  }
}

/** Permanently delete the signed-in account. Needs the password again. */
export async function deleteAccount(password: string): Promise<AuthResult> {
  try {
    return await parse(await post('/auth/delete-account', { password }));
  } catch {
    return { ok: false, error: 'Network error. Check your connection and try again.' };
  }
}
