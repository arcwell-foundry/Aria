import { createContext, useContext, type ReactNode } from 'react';
import { ThemeProvider as C1ThemeProvider } from '@thesysai/genui-sdk';

interface ThesysContextValue {
  enabled: boolean;
}

const ThesysContext = createContext<ThesysContextValue>({ enabled: false });

export function useThesys() {
  return useContext(ThesysContext);
}

interface ThesysProviderProps {
  children: ReactNode;
  enabled?: boolean;
}

export function ThesysProvider({ children, enabled = false }: ThesysProviderProps) {
  if (!enabled) {
    return (
      <ThesysContext.Provider value={{ enabled: false }}>
        {children}
      </ThesysContext.Provider>
    );
  }

  return (
    <ThesysContext.Provider value={{ enabled: true }}>
      <C1ThemeProvider>
        {children}
      </C1ThemeProvider>
    </ThesysContext.Provider>
  );
}
