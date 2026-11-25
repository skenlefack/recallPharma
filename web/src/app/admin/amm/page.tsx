import Link from "next/link";

import { ArrowRightIcon, SearchIcon } from "@/components/icons";
import { StatusBadge } from "@/components/regulatory";
import type { AdminAuthorisation } from "@/lib/admin";
import { type Jurisdiction, api, query } from "@/lib/api";

type Props = { searchParams: Promise<{ state?: string; jurisdiction?: string; q?: string }> };

const STATES = ["publiée", "proposée", "en première validation", "en seconde validation", "en litige", "archivée"];

export default async function AdminAuthorisations({ searchParams }: Props) {
  const { state = "", jurisdiction = "", q = "" } = await searchParams;
  const [rows, jurisdictions] = await Promise.all([
    api<AdminAuthorisation[]>(`/v1/admin/authorisations${query({ state, jurisdiction, q })}`),
    api<Jurisdiction[]>("/v1/jurisdictions"),
  ]);
  return (
    <>
      <header className="admin-head">
        <div>
          <span className="section-kicker">Référentiel</span>
          <h1>Autorisations de mise sur le marché</h1>
          <p className="muted">
            Toutes les AMM, publiées ou dans le circuit de validation. Les modifications passent par le circuit A → B → C.
          </p>
        </div>
        <div className="admin-head-actions">
          <Link href="/validation/nouvelle" className="admin-btn primary">
            Proposer une AMM <ArrowRightIcon size={14} />
          </Link>
        </div>
      </header>

      <form className="admin-toolbar" action="/admin/amm">
        <label className="admin-search">
          <SearchIcon size={16} />
          <input name="q" defaultValue={q} placeholder="Produit, n° d'AMM, titulaire" aria-label="Rechercher une AMM" />
        </label>
        <select name="state" defaultValue={state} className="admin-select" aria-label="État de publication">
          <option value="">Tous les états</option>
          {STATES.map((s) => (
            <option key={s}>{s}</option>
          ))}
        </select>
        <select name="jurisdiction" defaultValue={jurisdiction} className="admin-select" aria-label="Juridiction">
          <option value="">Toutes les juridictions</option>
          {jurisdictions.map((j) => (
            <option key={j.code} value={j.code}>
              {j.name}
            </option>
          ))}
        </select>
        <button type="submit" className="admin-btn primary">
          Filtrer
        </button>
        <span className="muted small">{rows.length} AMM</span>
      </form>

      <div className="admin-card admin-table-card">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Produit</th>
              <th>N° d&apos;AMM</th>
              <th>Juridiction</th>
              <th>Titulaire</th>
              <th>Publication</th>
              <th>Statut</th>
              <th>Vérifiée le</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <td>
                  {r.publication_state === "publiée" ? <Link href={`/amm/${r.id}`}>{r.product}</Link> : r.product}
                  {r.dispute_open && <span className="admin-chip danger">en litige</span>}
                </td>
                <td className="mono small">{r.ma_number}</td>
                <td>{r.jurisdiction}</td>
                <td className="small">{r.holder}</td>
                <td>
                  <span className={`admin-state ${r.publication_state === "publiée" ? "on" : "pending"}`}>{r.publication_state}</span>
                </td>
                <td>{r.status ? <StatusBadge status={r.status} /> : <span className="muted small">—</span>}</td>
                <td className="small">{r.last_verified_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
