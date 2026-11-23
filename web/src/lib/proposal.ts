/** Format d'une proposition (contrat /v1/curation) et lecture des 14 champs critiques côté écran. */
import type { components } from "./api-types";

export type PayloadIn = components["schemas"]["PayloadIn"];
export type Component = components["schemas"]["ComponentIn"];
export type EventIn = components["schemas"]["EventIn"];
export type WithdrawalIn = components["schemas"]["WithdrawalIn"];
export type SourceRef = components["schemas"]["SourceRef"];
export type Proposal = components["schemas"]["ProposalOut"];
export type DocumentOut = components["schemas"]["DocumentOut"];
export type Substance = components["schemas"]["SubstanceOut"];
export type Jurisdiction = components["schemas"]["JurisdictionOut"];

export const EVENT_TYPES: EventIn["type"][] = [
  "octroi",
  "renouvellement",
  "modification",
  "extension",
  "restriction",
  "transfert de titulaire",
  "suspension",
  "levée de suspension",
  "retrait d'office",
  "retrait à la demande du titulaire",
  "interdiction",
];
export const WITHDRAWAL_KINDS: WithdrawalIn["kind"][] = ["valeur", "interdit", "non renseigné", "conditionnel", "sans objet"];
export const WITHDRAWAL_UNITS: NonNullable<WithdrawalIn["unit"]>[] = ["jour", "heure", "degré-jour", "traite"];

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Loose = any;

/** Mêmes chemins que `CRITICAL_FIELDS` dans le domaine Python. */
export const CRITICAL_READERS: Record<string, (p: Loose) => unknown> = {
  denomination: (p) => p?.product?.name,
  ma_number: (p) => p?.ma_number,
  jurisdiction: (p) => p?.jurisdiction,
  events: (p) => p?.events,
  holder: (p) => p?.holder,
  components: (p) => p?.product?.components,
  pharmaceutical_form: (p) => p?.product?.pharmaceutical_form,
  routes: (p) => p?.product?.routes,
  target_species: (p) => p?.product?.target_species,
  posology: (p) => p?.spc?.posology,
  withdrawal_periods: (p) => p?.spc?.withdrawal_periods,
  prohibitions: (p) => (p?.spc?.restrictions ?? []).filter((r: Loose) => r.type === "interdiction"),
  contraindications: (p) => p?.spc?.contraindications,
  dispensing_condition: (p) => p?.dispensing_condition,
};

export function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) {
    if (!value.length) return "aucun";
    return value
      .map((v) =>
        typeof v === "object" && v
          ? Object.entries(v)
              .filter(([, x]) => x !== null && x !== "" && x !== undefined)
              .map(([k, x]) => `${k} : ${x}`)
              .join(", ")
          : String(v),
      )
      .join(" | ");
  }
  return String(value);
}

export function emptyPayload(): PayloadIn {
  return {
    jurisdiction: "PA",
    ma_number: "",
    procedure: "nationale",
    holder: "",
    manufacturer: null,
    dispensing_condition: "sur ordonnance vétérinaire",
    grant_date: "",
    expiry_date: null,
    renewal_pending: false,
    events: [],
    product: {
      id: null,
      name: "",
      designation: "",
      pharmaceutical_form: "",
      product_type: "pharmaceutique",
      routes: [],
      target_species: [],
      components: [],
    },
    spc: { languages: ["fr"], posology: "", contraindications: [], restrictions: [], withdrawal_periods: [] },
  };
}

export const STATE_TONE: Record<string, string> = {
  proposée: "gris",
  "en première validation": "bleu",
  "en seconde validation": "bleu",
  "en litige": "orange",
  publiée: "vert",
  archivée: "gris",
};
