import Link from "next/link";

import { ArrowRightIcon, CheckShieldIcon } from "@/components/icons";
import { type AuditPage, type Overview, actionLabel, formatDateTime } from "@/lib/admin";
import { api, query } from "@/lib/api";

type Props = { searchParams: Promise<{ before?: string; object_type?: string; who?: string }> };

const TYPES = ["account", "alert", "proposal", "authorisation", "document"];

export default async function AdminJournal({ searchParams }: Props) {
  const { before = "", object_type = "", who = "" } = await searchParams;
  const [page, o] = await Promise.all([
    api<AuditPage>(`/v1/admin/audit${query({ before, object_type, who, limit: "40" })}`),
    api<Overview>("/v1/admin/overview"),
  ]);
  return (
    <>
      <header className="admin-head">
        <div>
          <span className="section-kicker">Traçabilité</span>
          <h1>Journal d&apos;audit</h1>
          <p className="muted">Journal en ajout seul, chaque maillon scellé par l&apos;empreinte du précédent (SHA-256).</p>
        </div>
        <span className={`admin-integrity ${o.audit_chain_intact ? "ok" : "danger"}`}>
          <CheckShieldIcon size={18} /> {o.audit_chain_intact ? "Chaîne intacte" : "Chaîne rompue"}
        </span>
      </header>

      <form className="admin-toolbar" action="/admin/journal">
        <select name="object_type" defaultValue={object_type} className="admin-select" aria-label="Type d'objet">
          <option value="">Tous les objets</option>
          {TYPES.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <input name="who" defaultValue={who} placeholder="Compte (ex. cpt-09)" className="admin-input" aria-label="Auteur" />
        <button type="submit" className="admin-btn primary">
          Filtrer
        </button>
      </form>

      <div className="admin-card admin-table-card">
        <table className="admin-table">
          <thead>
            <tr>
              <th>N°</th>
              <th>Date</th>
              <th>Action</th>
              <th>Objet</th>
              <th>Auteur</th>
              <th>Détail</th>
            </tr>
          </thead>
          <tbody>
            {page.events.map((e) => (
              <tr key={e.seq}>
                <td className="mono small">{e.seq}</td>
                <td className="small">{formatDateTime(e.created_at)}</td>
                <td>
                  <strong>{actionLabel(e.action)}</strong>
                  {e.reason && <div className="small muted">{e.reason}</div>}
                </td>
                <td className="small">
                  {e.object_type} <span className="mono">{e.object_id}</span>
                </td>
                <td className="mono small">{e.actor}</td>
                <td>
                  {(e.before || e.after) && (
                    <details className="admin-diff">
                      <summary>Avant / après</summary>
                      {e.before && <pre>{JSON.stringify(e.before, null, 2)}</pre>}
                      {e.after && <pre>{JSON.stringify(e.after, null, 2)}</pre>}
                    </details>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {page.events.length === 0 && <p className="muted admin-empty">Aucune écriture pour ces filtres.</p>}
      </div>
      <div className="admin-pager">
        {before && (
          <Link href={`/admin/journal${query({ object_type, who })}`} className="admin-btn">
            Plus récentes
          </Link>
        )}
        {page.next_before && (
          <Link href={`/admin/journal${query({ object_type, who, before: String(page.next_before) })}`} className="admin-btn">
            Plus anciennes <ArrowRightIcon size={14} />
          </Link>
        )}
      </div>
    </>
  );
}
