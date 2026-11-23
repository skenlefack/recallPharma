import Link from "next/link";

import { type Alert, type Jurisdiction, api, query } from "@/lib/api";

type Props = { searchParams: Promise<{ jurisdiction?: string }> };

export default async function AlertsPage({ searchParams }: Props) {
  const { jurisdiction = "" } = await searchParams;
  const [alerts, jurisdictions] = await Promise.all([
    api<Alert[]>(`/v1/alerts${query({ jurisdiction })}`),
    api<Jurisdiction[]>("/v1/jurisdictions"),
  ]);
  return (
    <>
      <h1>Alertes</h1>
      <p className="muted">Suspensions, retraits, rappels de lots, produits falsifiés et informations de sécurité publiés.</p>
      <form className="row" action="/alertes">
        <label className="field">
          Juridiction
          <select name="jurisdiction" defaultValue={jurisdiction}>
            <option value="">Toutes</option>
            {jurisdictions.map((j) => (
              <option key={j.code} value={j.code}>
                {j.name}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="secondary">
          Filtrer
        </button>
      </form>
      <div className="stack" style={{ marginTop: 16 }}>
        {alerts.map((a) => (
          <div key={a.id} className={`banner tone-${a.level}`}>
            <div>
              <strong>{a.type}</strong> <span className="small">· {a.jurisdictions.join(", ")} · publiée le {a.published_at}</span>
              {a.closed_at && <span className="small"> · close le {a.closed_at}</span>}
              <div>{a.text}</div>
              {a.unlisted_product && <div className="small">Produit sans AMM : {a.unlisted_product}</div>}
              {a.authorisation_ids.length > 0 && (
                <div className="small">
                  {a.authorisation_ids.map((id) => (
                    <Link key={id} href={`/amm/${id}`} style={{ marginRight: 8 }}>
                      Voir la fiche {id}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
      </div>
    </>
  );
}
