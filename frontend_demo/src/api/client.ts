/**
 * Authenticated fetch wrapper.
 * Injects the Bearer token from localStorage on every request.
 * On 401, clears the stored token so the UI can prompt re-login.
 */
export async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const token = localStorage.getItem('nowva_access_token');
  const headers = new Headers(options.headers);

  if (token) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  if (!headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const response = await fetch(url, { ...options, headers });

  if (response.status === 401) {
    localStorage.removeItem('nowva_access_token');
  }

  return response;
}
