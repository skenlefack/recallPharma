import type { Me, Schemas } from "@/lib/api";

export type Overview = Schemas["Overview"];
export type AdminAccount = Schemas["AccountOut"];
export type AdminAuthorisation = Schemas["AuthorisationRow"];
export type AdminAlert = Schemas["AlertRow"];
export type Feedback = Schemas["FeedbackRow"];
export type AuditPage = Schemas["AuditPage"];
export type AuditRow = Schemas["AuditRow"];

/** Rôles qui ouvrent l'espace d'administration (mêmes règles que l'API, qui reste seule juge). */
export const ADMIN_ROLES = [
  "Administrateur fonctionnel",
  "Administrateur technique",
  "Auditeur",
  "Évaluateur de pharmacovigilance",
];

export const canAdmin = (me: Pick<Me, "roles"> | null) => !!me && me.roles.some((r) => ADMIN_ROLES.includes(r));

/** Libellés lisibles des actions du journal d'audit. */
export const ACTION_LABELS: Record<string, string> = {
  "account.created": "Compte créé",
  "account.roles_changed": "Rôles modifiés",
  "account.roles_synced": "Rôles synchronisés",
  "account.activated": "Compte réactivé",
  "account.deactivated": "Compte désactivé",
  "account.password_reset": "Mot de passe réinitialisé",
  "alert.published": "Alerte publiée",
  "alert.closed": "Alerte close",
};

export const actionLabel = (action: string) =>
  ACTION_LABELS[action] ?? action.replace(/[._]/g, " ").replace(":", " · ").replace(/^\w/, (c) => c.toUpperCase());

export const formatDateTime = (iso: string) =>
  new Intl.DateTimeFormat("fr-FR", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }).format(new Date(iso));
