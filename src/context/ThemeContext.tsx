import {
  createContext,
  useContext,
  useState,
  useEffect,
  useLayoutEffect,
  useMemo,
  type ReactNode,
} from "react";
import type { Theme, ThemeContextValue, ThemePreference } from "../types/ui";

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

const readSystemDark = () =>
  typeof window !== "undefined" &&
  window.matchMedia("(prefers-color-scheme: dark)").matches;

const readStoredPreference = (): ThemePreference => {
  if (typeof window === "undefined") return "system";

  const preference = localStorage.getItem("themePreference");
  const explicit = localStorage.getItem("themeExplicit") === "1";

  if (explicit && (preference === "light" || preference === "dark")) {
    return preference;
  }

  return "system";
};

const resolveTheme = (
  preference: ThemePreference,
  prefersDark: boolean,
): Theme => {
  if (preference === "system") return prefersDark ? "dark" : "light";
  return preference;
};

const applyDarkClass = (isDark: boolean) => {
  if (typeof document === "undefined") return;
  document.documentElement.classList.toggle("dark", isDark);
};

export const ThemeProvider = ({ children }: { children: ReactNode }) => {
  const [themePreference, setThemePreference] =
    useState<ThemePreference>("system");
  const [systemDark, setSystemDark] = useState(false);
  const [hasSynced, setHasSynced] = useState(false);

  useLayoutEffect(() => {
    setThemePreference(readStoredPreference());
    setSystemDark(readSystemDark());
    setHasSynced(true);
  }, []);

  const theme = useMemo<Theme>(() => {
    if (!hasSynced) return "light";
    return resolveTheme(themePreference, systemDark);
  }, [hasSynced, themePreference, systemDark]);

  useLayoutEffect(() => {
    if (!hasSynced) return;
    applyDarkClass(theme === "dark");
  }, [hasSynced, theme]);

  useEffect(() => {
    if (typeof window === "undefined") return;

    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) => {
      setSystemDark(event.matches);
      const explicit = localStorage.getItem("themeExplicit") === "1";
      if (!explicit) {
        applyDarkClass(event.matches);
      }
    };

    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (!hasSynced) return;

    localStorage.setItem("themePreference", themePreference);
    if (themePreference === "system") {
      localStorage.removeItem("themeExplicit");
    }
  }, [hasSynced, themePreference]);

  const setTheme = (next: ThemePreference) => {
    if (next === "system") {
      localStorage.removeItem("themeExplicit");
    } else {
      localStorage.setItem("themeExplicit", "1");
    }
    setThemePreference(next);
  };

  const toggleTheme = () => {
    localStorage.setItem("themeExplicit", "1");
    setThemePreference((prev) => {
      const resolved = resolveTheme(prev, systemDark);
      return resolved === "light" ? "dark" : "light";
    });
  };

  return (
    <ThemeContext.Provider
      value={{ theme, themePreference, setTheme, toggleTheme }}
    >
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = (): ThemeContextValue => {
  const value = useContext(ThemeContext);
  if (!value) {
    throw new Error("useTheme must be used within ThemeProvider");
  }
  return value;
};
