/** Base URL for API calls. Empty string = same origin (nginx /api/ proxy). */
export function resolveApiUrl(): string {
  const env = process.env.NEXT_PUBLIC_API_URL;
  if (env != null && env.length > 0) {
    return env.replace(/\/$/, "");
  }
  return process.env.NODE_ENV === "development" ? "http://localhost:8810" : "";
}

export const API_URL = resolveApiUrl();
