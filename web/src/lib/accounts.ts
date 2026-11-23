/** Comptes fictifs du jeu A10, déclarés dans le royaume Keycloak de développement (keycloak/realm-recallpharma.json). */
export const DEMO_PASSWORD = "demo-recallpharma";

export const DEMO_ACCOUNTS = [
  { id: "cpt-06", login: "demo06@recallpharma.example", role: "Validateur", hint: "Préparateur (A)" },
  { id: "cpt-13", login: "demo13@recallpharma.example", role: "Validateur", hint: "Premier validateur (B)" },
  { id: "cpt-07", login: "demo07@recallpharma.example", role: "Responsable réglementaire", hint: "Second validateur à l'aveugle (C)" },
  { id: "cpt-15", login: "demo15@recallpharma.example", role: "Responsable réglementaire", hint: "Arbitre" },
  { id: "cpt-10", login: "demo10@recallpharma.example", role: "Administrateur technique", hint: "Ne valide jamais (RG-32)" },
  { id: "cpt-03", login: "demo03@recallpharma.example", role: "Professionnel vérifié", hint: "Consultation" },
] as const;

export function accountLabel(id: string | null | undefined): string {
  const a = DEMO_ACCOUNTS.find((x) => x.id === id);
  return a ? `${a.role} · ${a.id}` : (id ?? "");
}
