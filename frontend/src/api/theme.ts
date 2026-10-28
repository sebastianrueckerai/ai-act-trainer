import type { paths } from "./schema";

export type ThemeResponse =
  paths["/api/theme"]["get"]["responses"]["200"]["content"]["application/json"];

export const getTheme = async (): Promise<ThemeResponse> => {
  const response = await fetch("/api/theme", { credentials: "same-origin" });
  if (!response.ok) throw new Error(`/api/theme -> HTTP ${response.status}`);
  return (await response.json()) as ThemeResponse;
};
