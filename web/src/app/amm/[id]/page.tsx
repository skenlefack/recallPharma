import Link from "next/link";
import { notFound } from "next/navigation";

import { AssessmentLine, Banners, NoticeBox } from "@/components/regulatory";
import { BatchCheckForm, ProposeUpdateButton, WithdrawalCalculator } from "@/components/SheetTools";
import { ApiError, type ProductSheet, type Schemas, api, query } from "@/lib/api";

type Props = { params: Promise<{ id: string }>; searchParams: Promise<{ as_of?: string; known_at?: string }> };

function withdrawalText(w: Schemas["WithdrawalOut"]) {
  switch (w.kind) {
    case "valeur":
      return Number(w.value) === 0 ? "aucun temps d'attente (zéro)" : `${Number(w.value)} ${w.unit}${Number(w.value) > 1 && w.unit !== "degré-jour" ? "s" : ""}`;
    case "interdit":
      return "usage interdit";
    case "non renseigné":
      return "non renseigné (ce n'est pas un délai nul)";
    default:
      return w.kind;
  }
}

export default async function SheetPage({ params, searchParams }: Props) {
  const { id } = await params;
  const { as_of, known_at } = await searchParams;
  let sheet: ProductSheet;
  try {
    sheet = await api<ProductSheet>(`/v1/authorisations/${encodeURIComponent(id)}${query({ as_of, known_at })}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  const { identity, regulation, assessment, spc } = sheet;
  // Texte d'origine du RCP, rubrique par rubrique : affiché dans sa langue, jamais traduit ni transposé (RG-06).
  const sections = spc
    ? await api<Schemas["SectionText"][]>(`/v1/authorisations/${encodeURIComponent(id)}/spc/sections`).catch(() => [])
    : [];
  const languages = [...new Set(sections.map((s) => s.language))];

  return (
    <>
      <p className="small">
        <Link href="/">← Recherche</Link>
      </p>
      <h1>
        {String(identity.name)} — {String(identity.designation)}
      </h1>
      <p className="muted">
        AMM <span className="mono">{String(regulation.ma_number)}</span> · {sheet.jurisdiction.name} · consultée au {sheet.as_of}
        {sheet.known_at && <> · telle que connue le {sheet.known_at}</>}
      </p>
      <div className="stack">
        <AssessmentLine assessment={assessment} />
        <Banners banners={assessment.banners} />
      </div>

      <nav className="tabs" aria-label="Vues de la fiche">
        <a href="#identite">Identité</a>
        <a href="#reglementation">Réglementation</a>
        <a href="#rcp">RCP et délais</a>
        <a href="#preuves">Preuves</a>
        <a href="#alertes">Alertes</a>
      </nav>

      <section id="identite">
        <h2>Identité</h2>
        <div className="card">
          <dl className="kv">
            <dt>Forme</dt>
            <dd>{String(identity.pharmaceutical_form)}</dd>
            <dt>Voies</dt>
            <dd>{(identity.routes as string[]).join(", ")}</dd>
            <dt>Espèces cibles</dt>
            <dd>{(identity.target_species as string[]).join(", ")}</dd>
          </dl>
          <h3>Composition</h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Substance</th>
                  <th>Teneur déclarée</th>
                  <th>Teneur normalisée</th>
                  <th>OMS 2024</th>
                  <th>OMSA</th>
                </tr>
              </thead>
              <tbody>
                {sheet.components.map((c) => (
                  <tr key={c.substance}>
                    <td>{c.substance}</td>
                    <td>{c.strength_as_stated}</td>
                    <td>{c.strength_value ? `${Number(c.strength_value)} ${c.strength_unit} ${c.strength_basis}` : "ambiguë"}</td>
                    <td>{c.who_category ?? "—"}</td>
                    <td>{c.woah_category ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section id="reglementation">
        <h2>Réglementation</h2>
        <div className="card">
          <dl className="kv">
            <dt>Procédure</dt>
            <dd>{String(regulation.procedure)}</dd>
            <dt>Titulaire</dt>
            <dd>{String(regulation.holder)}</dd>
            <dt>Fabricant</dt>
            <dd>{String(regulation.manufacturer ?? "—")}</dd>
            <dt>Délivrance</dt>
            <dd>{String(regulation.dispensing_condition ?? "—")}</dd>
            <dt>Octroi</dt>
            <dd>{String(regulation.grant_date)}</dd>
            <dt>Échéance</dt>
            <dd>
              {assessment.expiry_date ?? "illimitée"}
              {assessment.expiry_is_computed && <span className="muted"> (calculée : octroi + durée légale)</span>}
            </dd>
          </dl>
          <h3>Chronologie</h3>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Événement</th>
                  <th>Décision</th>
                  <th>Effet</th>
                  <th>Motif</th>
                </tr>
              </thead>
              <tbody>
                {sheet.events.map((e, i) => (
                  <tr key={i}>
                    <td>{e.type}</td>
                    <td>{e.decision_date}</td>
                    <td>
                      {e.effective_date}
                      {e.end_date && <span className="muted"> → {e.end_date}</span>}
                    </td>
                    <td>{e.reason ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section id="rcp">
        <h2>RCP et délais d&apos;attente</h2>
        {!spc ? (
          <NoticeBox>{sheet.spc_notice}</NoticeBox>
        ) : (
          <div className="stack">
            <div className="card">
              <p className="muted small" style={{ marginTop: 0 }}>
                Version {spc.version_label} · langues : {spc.languages.join(", ")}
              </p>
              {spc.posology && (
                <p>
                  <strong>Posologie :</strong> {spc.posology}
                </p>
              )}
              {spc.contraindications.length > 0 && (
                <p>
                  <strong>Contre-indications :</strong> {spc.contraindications.join(" ; ")}
                </p>
              )}
              {spc.restrictions.map((r, i) => (
                <div key={i} className="banner tone-rouge" style={{ marginBottom: 8 }}>
                  <span className="icon">⛔</span>
                  <div>{r.text}</div>
                </div>
              ))}
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Espèce</th>
                      <th>Denrée</th>
                      <th>Voie</th>
                      <th>Délai</th>
                    </tr>
                  </thead>
                  <tbody>
                    {spc.withdrawal_periods.map((w, i) => (
                      <tr key={i}>
                        <td>{w.species}</td>
                        <td>{w.commodity}</td>
                        <td>{w.route ?? "toutes"}</td>
                        <td>{withdrawalText(w)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            {spc.withdrawal_periods.length > 0 && <WithdrawalCalculator authorisationId={sheet.authorisation_id} periods={spc.withdrawal_periods} />}
            {languages.map((lang) => (
              <details key={lang} className="card" open={lang === languages[0]}>
                <summary>
                  Texte du RCP ({lang === "fr" ? "français" : lang === "en" ? "anglais" : lang}) ·{" "}
                  <span className="small muted">{sections.find((s) => s.language === lang)?.source_title}</span>
                </summary>
                <dl lang={lang}>
                  {sections
                    .filter((s) => s.language === lang)
                    .map((s) => (
                      <div key={s.rubric}>
                        <dt>
                          <strong>
                            {s.rubric}. {s.title}
                          </strong>{" "}
                          <span className="small muted">page {s.page ?? "—"}</span>
                        </dt>
                        <dd style={{ marginLeft: 0, marginBottom: 8 }}>{s.text}</dd>
                      </div>
                    ))}
                </dl>
              </details>
            ))}
          </div>
        )}
      </section>

      <section id="preuves">
        <h2>Preuves</h2>
        <div className="card">
          <dl className="kv">
            <dt>Niveau</dt>
            <dd>
              {assessment.evidence.level} · {assessment.evidence.label}
            </dd>
            <dt>Pour atteindre A</dt>
            <dd>{assessment.evidence.missing_for_a ?? "rien : niveau maximal"}</dd>
            <dt>Source</dt>
            <dd>
              {sheet.source ? (
                <>
                  {sheet.source.title} ({sheet.source.nature}, {sheet.source.document_date}
                  {sheet.source.latest_edition ? ", dernière édition" : ", édition non à jour"})
                </>
              ) : (
                "aucune source exploitable"
              )}
            </dd>
            <dt>Validations</dt>
            <dd>{String(regulation.validations)}</dd>
            <dt>Dernière vérification</dt>
            <dd>{String(regulation.last_verified_at)}</dd>
          </dl>
          <p style={{ marginBottom: 0 }}>
            <ProposeUpdateButton authorisationId={sheet.authorisation_id} />
          </p>
        </div>
      </section>

      <section id="alertes">
        <h2>Alertes et lots</h2>
        <div className="stack">
          {sheet.alerts.length === 0 && <p className="muted">Aucune alerte publiée connue pour cette AMM.</p>}
          {sheet.alerts.map((a) => (
            <div key={a.id} className={`banner tone-${a.level}`}>
              <div>
                <strong>{a.type}</strong> <span className="muted small">publiée le {a.published_at}</span>
                {a.closed_at && <span className="small"> · close le {a.closed_at}</span>}
                <div>{a.text}</div>
                {a.batch_numbers.length > 0 && <div className="small mono">Lots : {a.batch_numbers.join(", ")}</div>}
              </div>
            </div>
          ))}
          <BatchCheckForm authorisationId={sheet.authorisation_id} />
        </div>
      </section>
    </>
  );
}
