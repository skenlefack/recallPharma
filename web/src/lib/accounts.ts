/** Comptes fictifs du jeu A10, pour la démonstration. Keycloak (OIDC, PKCE, MFA) les remplacera. */
export const DEMO_ACCOUNTS = [
  { id: "cpt-06", role: "Validateur", hint: "Préparateur (A)" },
  { id: "cpt-13", role: "Validateur", hint: "Premier validateur (B)" },
  { id: "cpt-07", role: "Responsable réglementaire", hint: "Second validateur à l'aveugle (C)" },
  { id: "cpt-15", role: "Responsable réglementaire", hint: "Arbitre" },
  { id: "cpt-10", role: "Administrateur technique", hint: "Ne valide jamais (RG-32)" },
  { id: "cpt-03", role: "Professionnel vérifié", hint: "Consultation" },
] as const;

export function accountLabel(id: string | null | undefined): string {
  const a = DEMO_ACCOUNTS.find((x) => x.id === id);
  return a ? `${a.role} · ${a.id}` : (id ?? "");
}
