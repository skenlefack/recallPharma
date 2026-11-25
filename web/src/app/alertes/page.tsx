import Link from "next/link";

import {
  AlertTriangleIcon,
  ArrowRightIcon,
  BanIcon,
  CheckShieldIcon,
  InfoIcon,
  MapPinIcon,
  PackageIcon,
  PauseIcon,
} from "@/components/icons";
import { PageBanner } from "@/components/PageBanner";
import { type Alert, type Jurisdiction, api, query } from "@/lib/api";

type Props = { searchParams: Promise<{ jurisdiction?: string }> };

const MONTHS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."];

const LEVEL_LABEL: Record<string, string> = { rouge: "Critique", orange: "À surveiller" };

/** Icône selon le type d'alerte (libellés du registre). */
function typeIcon(type: string) {
  if (type.includes("falsifi")) return CheckShieldIcon;
  if (type.includes("rappel")) return PackageIcon;
  if (type.includes("suspension")) return PauseIcon;
  if (type.includes("retrait")) return BanIcon;
  if (type.includes("sécurité")) return AlertTriangleIcon;
  return InfoIcon;
}

function tone(a: Alert) {
  if (a.closed_at) return "closed";
  return a.level === "rouge" || a.level === "orange" ? a.level : "info";
}

export default async function AlertsPage({ searchParams }: Props) {
  const { jurisdiction = "" } = await searchParams;
  const [alerts, jurisdictions] = await Promise.all([
    api<Alert[]>(`/v1/alerts${query({ jurisdiction })}`),
    api<Jurisdiction[]>("/v1/jurisdictions"),
  ]);
  const names = new Map(jurisdictions.map((j) => [j.code, j.name]));
  const open = alerts.filter((a) => !a.closed_at);
  const summary = [
    { key: "rouge", value: open.filter((a) => a.level === "rouge").length, label: "critiques en cours" },
    { key: "orange", value: open.filter((a) => a.level === "orange").length, label: "à surveiller" },
    { key: "closed", value: alerts.length - open.length, label: "closes" },
  ];

  return (
    <>
      <PageBanner eyebrow="Pharmacovigilance" title="Alertes">
        Suspensions, retraits, rappels de lots, produits falsifiés et informations de sécurité publiés.
      </PageBanner>

      <div className="section-title">
        <span className="section-kicker">Fil de pharmacovigilance</span>
        <h2>Alertes publiées</h2>
        <p>Les plus récentes en premier, avec leur juridiction et les fiches concernées</p>
      </div>

      <div className="alert-summary">
        {summary.map((s) => (
          <div key={s.key} className={`alert-stat lvl-${s.key}`}>
            <strong>{s.value}</strong>
            <span>{s.label}</span>
          </div>
        ))}
      </div>

      <nav className="alert-filter" aria-label="Filtrer par juridiction">
        <Link href="/alertes" aria-current={jurisdiction === "" ? "page" : undefined}>
          Toutes
        </Link>
        {jurisdictions.map((j) => (
          <Link
            key={j.code}
            href={`/alertes${query({ jurisdiction: j.code })}`}
            aria-current={jurisdiction === j.code ? "page" : undefined}
          >
            {j.name}
          </Link>
        ))}
      </nav>

      {alerts.length === 0 && <p className="muted alert-empty">Aucune alerte publiée pour cette juridiction.</p>}

      <ol className="alert-timeline">
        {alerts.map((a) => {
          const Icon = typeIcon(a.type);
          const [y, m, d] = a.published_at.split("-");
          const t = tone(a);
          return (
            <li key={a.id} className={`alert-item lvl-${t}`}>
              <time className="alert-date" dateTime={a.published_at}>
                <strong>{d}</strong>
                <span>
                  {MONTHS[Number(m) - 1]} {y}
                </span>
              </time>
              <article className="alert-card">
                <span className="alert-icon" aria-hidden>
                  <Icon size={24} />
                </span>
                <div className="alert-body">
                  <div className="alert-head">
                    <span className="alert-type">{a.type}</span>
                    <span className="alert-level">{a.closed_at ? "Close" : (LEVEL_LABEL[a.level] ?? "Information")}</span>
                  </div>
                  <p className="alert-text">{a.text}</p>
                  {a.unlisted_product && (
                    <p className="alert-product">
                      <strong>Produit sans AMM</strong> {a.unlisted_product}
                    </p>
                  )}
                  <div className="alert-meta">
                    {a.jurisdictions.map((c) => (
                      <span key={c} className="alert-chip">
                        <MapPinIcon size={14} /> {names.get(c) ?? c}
                      </span>
                    ))}
                    {a.closed_at && <span className="alert-chip">Close le {a.closed_at}</span>}
                    {a.authorisation_ids.map((id) => (
                      <Link key={id} href={`/amm/${id}`} className="alert-link">
                        Voir la fiche {id} <ArrowRightIcon size={14} />
                      </Link>
                    ))}
                  </div>
                </div>
              </article>
            </li>
          );
        })}
      </ol>
    </>
  );
}
