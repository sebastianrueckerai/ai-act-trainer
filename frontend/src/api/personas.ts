import type { paths } from "./schema";

export type PersonaCard =
  paths["/api/personas"]["get"]["responses"]["200"]["content"]["application/json"][number];

export async function getPersonas(): Promise<PersonaCard[]> {
  const response = await fetch("/api/personas", { credentials: "same-origin" });
  if (!response.ok) throw new Error(`/api/personas -> HTTP ${response.status}`);
  return (await response.json()) as PersonaCard[];
}
