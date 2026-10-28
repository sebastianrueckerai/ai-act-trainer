import type { paths } from "./schema";

export type VersionInfo =
  paths["/api/version"]["get"]["responses"]["200"]["content"]["application/json"];
export type Me = paths["/api/me"]["get"]["responses"]["200"]["content"]["application/json"];
export type AuthOptions =
  paths["/api/auth/options"]["get"]["responses"]["200"]["content"]["application/json"];
export type DevUser =
  paths["/api/auth/dev/users"]["get"]["responses"]["200"]["content"]["application/json"][number];

async function getJson<T>(url: string, acceptable: number[] = []): Promise<T | null> {
  const response = await fetch(url, { credentials: "same-origin" });
  if (acceptable.includes(response.status)) return null;
  if (!response.ok) throw new Error(`${url} -> HTTP ${response.status}`);
  return (await response.json()) as T;
}

async function postJson(url: string, body?: unknown): Promise<void> {
  const response = await fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: { "content-type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${url} -> HTTP ${response.status}`);
}

export const getVersion = () => getJson<VersionInfo>("/api/version") as Promise<VersionInfo>;
export const getMe = () => getJson<Me>("/api/me", [401]);
export const getAuthOptions = () =>
  getJson<AuthOptions>("/api/auth/options") as Promise<AuthOptions>;
export const getDevUsers = () => getJson<DevUser[]>("/api/auth/dev/users", [404]);
export const devLogin = (subject: string) => postJson("/api/auth/dev/login", { subject });
export const guestLogin = () => postJson("/api/auth/guest");
export const logout = () => postJson("/api/auth/logout");
// Typed by hand: the schema is generated from the dev backend, which has no invite route.
export const inviteLogin = (token: string) => postJson("/api/auth/invite/login", { token });
