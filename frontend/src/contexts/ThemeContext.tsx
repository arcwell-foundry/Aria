import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  type ReactNode,
} from "react";
import { useLocation } from "react-router-dom";

type Theme = "dark" | "light";

interface ThemeContextType {
  theme: Theme;
}

const ThemeContext = createContext<ThemeContextType | null>(null);

function getThemeForRoute(pathname: string): Theme {
  const darkRoutes = ["/", "/briefing", "/dialogue"];

  if (pathname === "/") return "dark";
  if (darkRoutes.some((r) => r !== "/" && pathname.startsWith(r))) return "dark";

  return "light";
}

interface ThemeProviderProps {
  children: ReactNode;
}

export function ThemeProvider({ children }: ThemeProviderProps) {
  const { pathname } = useLocation();

  const theme = useMemo(() => getThemeForRoute(pathname), [pathname]);

  useEffect(() => {
    const root = document.documentElement;

    if (theme === "light") {
      root.classList.add("light");
    } else {
      root.classList.remove("light");
    }

    root.setAttribute("data-theme", theme);
  }, [theme]);

  const value = useMemo<ThemeContextType>(() => ({ theme }), [theme]);

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextType {
  const context = useContext(ThemeContext);
  if (context === null) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
