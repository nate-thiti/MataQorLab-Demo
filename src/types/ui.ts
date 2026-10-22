export type LocaleRouting = {
  locale: string;
  localePrefix: string;
  absolutePrefix: string;
};

export type Theme = "light" | "dark";
export type ThemePreference = "light" | "dark" | "system";

export type ThemeContextValue = {
  theme: Theme;
  themePreference: ThemePreference;
  setTheme: (next: ThemePreference) => void;
  toggleTheme: () => void;
};
