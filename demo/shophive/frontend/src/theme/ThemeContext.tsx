import React, { createContext, useContext, useEffect, useState } from 'react';

export type ThemeName = 'light' | 'dark';

interface ThemeValue {
  theme: ThemeName;
  setTheme: (theme: ThemeName) => void;
}

const STORAGE_KEY = 'shophive.theme';
const ThemeContext = createContext<ThemeValue | null>(null);

function initialTheme(): ThemeName {
  try {
    return localStorage.getItem(STORAGE_KEY) === 'dark' ? 'dark' : 'light';
  } catch {
    return 'light';
  }
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<ThemeName>(initialTheme);

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark');
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Storage can be blocked (private mode). The theme still works for this visit.
    }
  }, [theme]);

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  const value = useContext(ThemeContext);
  if (!value) throw new Error('useTheme must be used inside <ThemeProvider>');
  return value;
}

