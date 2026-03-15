const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export interface AuthTokens {
  access_token: string;
  token_type: string;
}

export interface UserProfile {
  id: string;
  username: string;
  name: string;
  email: string;
  created_at: string;
}

export const authApi = {
  async register(name: string, email: string, password: string): Promise<UserProfile> {
    const response = await fetch(`${API_BASE_URL}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, email, password }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Registration failed');
    }

    return response.json();
  },

  async login(email: string, password: string): Promise<AuthTokens> {
    // OAuth2PasswordRequestForm expects form-encoded data with "username" field
    const body = new URLSearchParams();
    body.append('username', email);
    body.append('password', password);

    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: body.toString(),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || 'Login failed');
    }

    const tokens: AuthTokens = await response.json();
    this.setToken(tokens.access_token);
    return tokens;
  },

  getToken(): string | null {
    return localStorage.getItem('nowva_access_token');
  },

  setToken(token: string): void {
    localStorage.setItem('nowva_access_token', token);
  },

  clearToken(): void {
    localStorage.removeItem('nowva_access_token');
  },

  isLoggedIn(): boolean {
    return !!localStorage.getItem('nowva_access_token');
  },
};
