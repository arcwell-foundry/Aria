import {
  createContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import type { User, SignupData, LoginData } from "@/api/auth";
import * as authApi from "@/api/auth";

export interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (data: LoginData) => Promise<void>;
  logout: () => Promise<void>;
  signup: (data: SignupData) => Promise<void>;
}

export const AuthContext = createContext<AuthContextType | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const isAuthenticated = user !== null;

  // Check for existing session on mount
  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem("access_token");
      if (token) {
        try {
          const userData = await authApi.getCurrentUser();
          setUser(userData);
        } catch (error: unknown) {
          // Only clear tokens on auth failures (401/403), not server errors.
          // The axios response interceptor already handles 401 token refresh,
          // so if we get here with a 401 the refresh also failed.
          const status =
            error && typeof error === "object" && "response" in error
              ? (error as { response?: { status?: number } }).response?.status
              : undefined;
          if (status === 401 || status === 403) {
            localStorage.removeItem("access_token");
            localStorage.removeItem("refresh_token");
          }
          // For server errors (500, network), keep tokens — the server
          // may recover and the token is still valid.
        }
      }
      setIsLoading(false);
    };

    checkAuth();
  }, []);

  const login = useCallback(async (data: LoginData) => {
    const response = await authApi.login(data);
    localStorage.setItem("access_token", response.access_token);
    localStorage.setItem("refresh_token", response.refresh_token);

    const userData = await authApi.getCurrentUser();
    setUser(userData);
  }, []);

  const signup = useCallback(async (data: SignupData) => {
    const response = await authApi.signup(data);
    localStorage.setItem("access_token", response.access_token);
    localStorage.setItem("refresh_token", response.refresh_token);

    const userData = await authApi.getCurrentUser();
    setUser(userData);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch {
      // Ignore logout errors
    }
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, isLoading, isAuthenticated, login, logout, signup }}
    >
      {children}
    </AuthContext.Provider>
  );
}
