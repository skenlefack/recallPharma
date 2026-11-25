import type { Schemas } from "@/lib/api";

type Assessment = Schemas["AssessmentOut"];
type Banner = Schemas["BannerOut"];

const STATUS_TONE: Record<string, string> = {
  valide: "vert",
  suspendue: "rouge",
  retirée: "rouge",
  "renouvellement en instance": "orange",
  "expirée, à confirmer": "orange",
  "non vérifiable": "gris",
};

/** Couleur du statut, pour les liserés ; toujours doublée du badge qui porte le libellé. */
export const statusTone = (status: string) => STATUS_TONE[status] ?? "gris";

const LEVEL_ICON: Record<string, string> = { rouge: "⛔", orange: "⚠", gris: "ⓘ" };
const LEVEL_LABEL: Record<string, string> = { rouge: "Alerte", orange: "Attention", gris: "Information" };

/** Statut calculé (RG-03) : « non trouvé », « suspendu », « retiré », « expiré » ne sont jamais confondus. */
export function StatusBadge({ status }: { status: string }) {
  return <span className={`badge tone-${STATUS_TONE[status] ?? "gris"}`}>AMM {status}</span>;
}

export function EvidenceBadge({ evidence }: { evidence: Assessment["evidence"] }) {
  const tone = { A: "vert", B: "orange", C: "bleu", D: "gris" }[evidence.level] ?? "gris";
  return (
    <span className={`badge tone-${tone}`} title={evidence.missing_for_a ? `Pour atteindre A : ${evidence.missing_for_a}` : undefined}>
      Preuve {evidence.level} · {evidence.label}
    </span>
  );
}

export function BannerItem({ banner }: { banner: Banner }) {
  return (
    <div className={`banner tone-${banner.level}`} role={banner.level === "rouge" ? "alert" : "note"}>
      <span className="icon" aria-hidden>
        {LEVEL_ICON[banner.level] ?? "ⓘ"}
      </span>
      <div>
        <strong>{LEVEL_LABEL[banner.level] ?? "Information"}</strong>
        <span className="rule">{banner.rule}</span>
        <div>{banner.text}</div>
      </div>
    </div>
  );
}

export function Banners({ banners }: { banners: Banner[] }) {
  if (!banners.length) return null;
  return (
    <div className="stack">
      {banners.map((b, i) => (
        <BannerItem key={`${b.rule}-${i}`} banner={b} />
      ))}
    </div>
  );
}

export function AssessmentLine({ assessment }: { assessment: Assessment }) {
  return (
    <div className="row" style={{ alignItems: "center" }}>
      <StatusBadge status={assessment.status} />
      <EvidenceBadge evidence={assessment.evidence} />
      {assessment.mentions.map((m) => (
        <span key={m} className="badge tone-orange">
          {m}
        </span>
      ))}
    </div>
  );
}

export function NoticeBox({ children }: { children: React.ReactNode }) {
  return (
    <div className="banner tone-gris" role="note">
      <span className="icon" aria-hidden>
        ⓘ
      </span>
      <div>{children}</div>
    </div>
  );
}
