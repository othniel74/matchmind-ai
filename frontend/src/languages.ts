// Mirrors GET /api/languages (backend/app/languages.py). Add a language there first.
export const LANGUAGES = [
  { code: "en", native: "English", direction: "ltr" },
  { code: "es", native: "Español", direction: "ltr" },
  { code: "fr", native: "Français", direction: "ltr" },
  { code: "pt", native: "Português (Brasil)", direction: "ltr" },
  { code: "de", native: "Deutsch", direction: "ltr" },
  { code: "it", native: "Italiano", direction: "ltr" },
  { code: "ar", native: "العربية", direction: "rtl" },
] as const;

export type LanguageCode = (typeof LANGUAGES)[number]["code"];

export const directionOf = (code: string): "ltr" | "rtl" =>
  LANGUAGES.find((l) => l.code === code)?.direction ?? "ltr";
