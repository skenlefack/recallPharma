import Link from "next/link";

import { AssessmentLine, NoticeBox } from "@/components/regulatory";
import { ApiError, type Jurisdiction, type SearchResult, api, query } from "@/lib/api";

type Props = { searchParams: Promise<{ q?: string; jurisdiction?: string; as_of?: string }> };

export default async function SearchPage({ searchParams }: Props) {
  const { q = "", jurisdiction = "", as_of = "" } = await searchParams;
  const jurisdictions = await api<Jurisdiction[]>("/v1/jurisdictions");
  let result: SearchResult | null = null;
  let error: string | null = null;
  if (q.trim().length >= 2) {
    try {
      result = await api<SearchResult>(`/v1/search${query({ q, jurisdiction, as_of })}`);
    } catch (e) {
      error = e instanceof ApiError ? e.message : "Recherche indisponible";
    }
  }

  return (
    <>
      <h1>Rechercher un médicament vétérinaire</h1>
      <p className="muted">Par nom, substance, numéro d&apos;AMM ou titulaire. Les fautes de frappe et les accents sont tolérés.</p>
      <form className="card row" role="search" action="/">
        <label className="field" style={{ flex: "2 1 260px" }}>
          Recherche
          <input name="q" defaultValue={q} placeholder="ex. oxytétracycline, PA-V-2023-0002" minLength={2} required />
        </label>
        <label className="field" style={{ flex: "1 1 160px" }}>
          Juridiction
          <select name="jurisdiction" defaultValue={jurisdiction}>
            <option value="">Toutes</option>
            {jurisdictions.map((j) => (
              <option key={j.code} value={j.code}>
                {j.name} ({j.code})
              </option>
            ))}
          </select>
        </label>
        <label className="field" style={{ flex: "1 1 150px" }}>
          À la date du
          <input type="date" name="as_of" defaultValue={as_of} />
        </label>
        <button type="submit">Rechercher</button>
      </form>

      {error && <p className="error">{error}</p>}
      {result && (
        <section aria-live="polite">
          <h2>
            {result.hits.length} résultat{result.hits.length > 1 ? "s" : ""}{" "}
            <span className="muted small">au {result.as_of}</span>
          </h2>
          {result.notice && <NoticeBox>{result.notice}</NoticeBox>}
          {result.hits.length === 0 && !result.notice && (
            <NoticeBox>Aucune AMM publiée ne correspond. L&apos;absence de résultat ne signifie pas une interdiction.</NoticeBox>
          )}
          <div className="stack" style={{ marginTop: 12 }}>
            {result.hits.map((h) => (
              <Link key={h.authorisation_id} href={`/amm/${h.authorisation_id}${query({ as_of })}`} className="card hit">
                <div className="row" style={{ justifyContent: "space-between", alignItems: "center" }}>
                  <span className="title">
                    {h.product_name} — {h.designation}
                  </span>
                  <span className="mono small">{h.ma_number}</span>
                </div>
                <div className="muted small">
                  {h.holder} · {h.substances.join(", ")} · juridiction {h.jurisdiction}
                  {!h.applies_to_requested && <strong> · AMM étrangère à la juridiction demandée</strong>}
                </div>
                <div style={{ marginTop: 8 }}>
                  <AssessmentLine assessment={h.assessment} />
                </div>
                {h.assessment.banners.some((b) => b.level === "rouge") && (
                  <div className="small" style={{ marginTop: 6, color: "var(--red-fg)" }}>
                    ⛔ {h.assessment.banners.find((b) => b.level === "rouge")?.text}
                  </div>
                )}
              </Link>
            ))}
          </div>
        </section>
      )}
    </>
  );
}
