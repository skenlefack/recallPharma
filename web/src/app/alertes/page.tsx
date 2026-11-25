import Link from "next/link";
import { PageBanner } from "@/components/PageBanner";

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
      <PageBanner eyebrow="Pharmacovigilance" title="Alertes">
        Suspensions, retraits, rappels de lots, produits falsifiés et informations de sécurité publiés.
      </PageBanner>
      <form className="card row" action="/alertes" style={{ width: "fit-content" }}>
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
            <span className="icon" aria-hidden>
              {a.level === "rouge" ? "⛔" : a.level === "orange" ? "⚠" : "ⓘ"}
            </span>
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
