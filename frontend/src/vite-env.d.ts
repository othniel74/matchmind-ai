/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** "true" shows the real-data research views (local use only; the product uses synthetic data). */
  readonly VITE_ENABLE_RESEARCH?: string;
}
