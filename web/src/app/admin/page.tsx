import Link from "next/link";

import {
  ArrowRightIcon,
  BellIcon,
  ChatIcon,
  CheckShieldIcon,
  DocumentIcon,
  HistoryIcon,
  PillIcon,
  PlusIcon,
  UsersIcon,
} from "@/components/icons";
import { type AuditPage, type Overview, actionLabel, formatDateTime } from "@/lib/admin";
import { type Jurisdiction, api } from "@/lib/api";

const STATUS_TONE: Record<string, string> = {
  valide: "ok",
  suspendue: "danger",
  retirée: "danger",
  "expirée, à confirmer": "warn",
  "renouvellement en instance": "warn",
};

const sum = (o: Record<string, number>) => Object.values(o).reduce((a, b) => a + b, 0);

/** Barres horizontales proportionnelles (pas de bibliothèque de graphiques). */
function Bars({ data, tones, labels }: { data: Record<string, number>; tones?: Record<string, string>; labels?: Map<string, string> }) {
  const max = Math.max(1, ...Object.values(data));
  const rows = Object.entries(data).sort((a, b) => b[1] - a[1]);
  return (
    <ul className="admin-bars">
      {rows.map(([key, value]) => (
        <li key={key}>
          <span className="admin-bars-label">{labels?.get(key) ?? key}</span>
          <span className="admin-bars-track">
            <span className={`admin-bars-fill tone-${tones?.[key] ?? "brand"}`} style={{ width: `${(value / max) * 100}%` }} />
          </span>
          <strong>{value}</strong>
        </li>
      ))}
    </ul>
  );
}

export default async function AdminDashboard() {
  const [o, audit, jurisdictions] = await Promise.all([
    api<Overview>("/v1/admin/overview"),
    api<AuditPage>("/v1/admin/audit?limit=8"),
    api<Jurisdiction[]>("/v1/jurisdictions"),
  ]);
  const names = new Map(jurisdictions.map((j) => [j.code, j.name]));
  const published = o.authorisations["publiée"] ?? 0;
  const pending = sum(o.proposals);
  const openAlerts = sum(o.alerts_open);
  const activeAccounts = sum(o.accounts);
  const kpis = [
    { icon: PillIcon, label: "AMM publiées", value: published, hint: `${sum(o.authorisations) - published} hors publication`, href: "/admin/amm" },
    { icon: DocumentIcon, label: "Propositions en cours", value: pending, hint: `${o.documents} documents sources`, href: "/validation" },
    { icon: BellIcon, label: "Alertes ouvertes", value: openAlerts, hint: `${o.alerts_open["rouge"] ?? 0} critiques · ${o.alerts_closed} closes`, href: "/admin/alertes", tone: "danger" },
    { icon: UsersIcon, label: "Rôles attribués", value: activeAccounts, hint: `${o.accounts_inactive} compte(s) désactivé(s)`, href: "/admin/comptes" },
    { icon: ChatIcon, label: "Questions au Copilot (30 j)", value: o.copilot.questions_30j ?? 0, hint: `${o.copilot.erreurs ?? 0} signalement(s) d'erreur`, href: "/admin/copilot" },
    { icon: HistoryIcon, label: "Écritures auditées (7 j)", value: o.audit_last_7_days, hint: o.audit_chain_intact ? "Chaîne d'audit intacte" : "Chaîne d'audit rompue", href: "/admin/journal", tone: o.audit_chain_intact ? "ok" : "danger" },
  ];

  return (
    <>
      <header className="admin-head">
        <div>
          <span className="section-kicker">Vue d&apos;ensemble</span>
          <h1>Tableau de bord</h1>
          <p className="muted">Situation du référentiel au {o.as_of}.</p>
        </div>
        <div className="admin-head-actions">
          {o.permissions.includes("comptes") && (
            <Link href="/admin/comptes#nouveau" className="admin-btn">
              <PlusIcon size={16} /> Nouveau compte
            </Link>
          )}
          {o.permissions.includes("alertes") && (
            <Link href="/admin/alertes#nouvelle" className="admin-btn primary">
              <BellIcon size={16} /> Publier une alerte
            </Link>
          )}
        </div>
      </header>

      <section className="admin-kpis">
        {kpis.map(({ icon: Icon, label, value, hint, href, tone }) => (
          <Link key={label} href={href} className={`admin-kpi${tone ? ` tone-${tone}` : ""}`}>
            <span className="admin-kpi-icon">
              <Icon size={22} />
            </span>
            <span className="admin-kpi-value">{value}</span>
            <span className="admin-kpi-label">{label}</span>
            <span className="admin-kpi-hint">{hint}</span>
          </Link>
        ))}
      </section>

      <section className="admin-grid">
        <div className="admin-card">
          <h2>Statut des AMM publiées</h2>
          <Bars data={o.statuses} tones={STATUS_TONE} />
        </div>
        <div className="admin-card">
          <h2>AMM publiées par juridiction</h2>
          <Bars data={o.by_jurisdiction} labels={names} />
        </div>
        <div className="admin-card">
          <h2>Comptes actifs par rôle</h2>
          <Bars data={o.accounts} />
        </div>
        <div className="admin-card">
          <h2>Circuit de validation</h2>
          {pending === 0 ? (
            <p className="muted">Aucune proposition en cours.</p>
          ) : (
            <Bars data={o.proposals} tones={{ "en litige": "danger" }} />
          )}
          <h2 style={{ marginTop: 22 }}>Alertes ouvertes par niveau</h2>
          <Bars data={o.alerts_open} tones={{ rouge: "danger", orange: "warn", gris: "muted" }} />
        </div>
      </section>

      <section className="admin-card">
        <div className="admin-card-head">
          <h2>Dernières écritures</h2>
          <Link href="/admin/journal" className="admin-link">
            Tout le journal <ArrowRightIcon size={14} />
          </Link>
        </div>
        <ol className="admin-feed">
          {audit.events.map((e) => (
            <li key={e.seq}>
              <span className="admin-feed-dot" aria-hidden>
                <CheckShieldIcon size={14} />
              </span>
              <div>
                <strong>{actionLabel(e.action)}</strong> · {e.object_type} <span className="mono">{e.object_id}</span>
                {e.reason && <span className="muted"> — {e.reason}</span>}
                <div className="small muted">
                  {formatDateTime(e.created_at)} · par <span className="mono">{e.actor}</span>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
