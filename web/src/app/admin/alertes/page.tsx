import { AlertsManager } from "@/components/admin/AlertsManager";
import type { AdminAlert, Overview } from "@/lib/admin";
import { type Jurisdiction, api } from "@/lib/api";

export default async function AdminAlerts() {
  const [alerts, jurisdictions, overview] = await Promise.all([
    api<AdminAlert[]>("/v1/alerts"),
    api<Jurisdiction[]>("/v1/jurisdictions"),
    api<Overview>("/v1/admin/overview"),
  ]);
  return (
    <>
      <header className="admin-head">
        <div>
          <span className="section-kicker">Pharmacovigilance</span>
          <h1>Alertes</h1>
          <p className="muted">
            Publier une suspension, un retrait, un rappel de lot, un produit falsifié ou une information de sécurité, et
            clore une alerte avec son motif. L&apos;alerte apparaît aussitôt sur les fiches concernées.
          </p>
        </div>
      </header>
      <AlertsManager initial={alerts} jurisdictions={jurisdictions} canManage={overview.permissions.includes("alertes")} />
    </>
  );
}
