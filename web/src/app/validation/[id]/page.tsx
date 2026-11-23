import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import { ProposalEditor } from "@/components/ProposalEditor";
import { ArbitrationPanel, BlindEntryPanel, FirstValidationPanel, SubmitPanel } from "@/components/WorkflowPanels";
import { accountLabel } from "@/lib/accounts";
import { ApiError, type Jurisdiction, type Substance, api, currentUser } from "@/lib/api";
import { CRITICAL_READERS, type DocumentOut, type PayloadIn, type Proposal, type SourceRef, STATE_TONE, display } from "@/lib/proposal";

type Step = { actor: string; action: string; from: string; to: string; detail: Record<string, unknown>; at: string };
type Props = { params: Promise<{ id: string }> };

export default async function ProposalPage({ params }: Props) {
  const { id } = await params;
  const user = await currentUser();
  if (!user) redirect(`/connexion?next=/validation/${id}`);
  let proposal: Proposal;
  try {
    proposal = await api<Proposal>(`/v1/curation/proposals/${encodeURIComponent(id)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) notFound();
    throw e;
  }
  const [history, substances, documents, jurisdictions] = await Promise.all([
    api<Step[]>(`/v1/curation/proposals/${proposal.id}/history`),
    api<Substance[]>("/v1/substances"),
    api<DocumentOut[]>("/v1/curation/documents"),
    api<Jurisdiction[]>("/v1/jurisdictions"),
  ]);
  const p = proposal;
  const isPreparer = p.prepared_by === user;
  const involved = [p.prepared_by, p.first_validator, p.second_validator].includes(user);

  return (
    <>
      <p className="small">
        <Link href="/validation">← Validation</Link>
      </p>
      <h1>
        Proposition #{p.id} <span className={`badge tone-${STATE_TONE[p.state]}`}>{p.state}</span>
      </h1>
      <p className="muted">
        Révision {p.revision} · {p.origin}
        {p.authorisation_id && (
          <>
            {" "}
            · AMM <Link href={`/amm/${p.authorisation_id}`}>{p.authorisation_id}</Link>
          </>
        )}
        <br />
        A : {accountLabel(p.prepared_by)}
        {p.first_validator && <> · B : {accountLabel(p.first_validator)}</>}
        {p.second_validator && <> · C : {accountLabel(p.second_validator)}</>}
        {p.arbiter && <> · arbitre : {accountLabel(p.arbiter)}</>}
      </p>

      {p.state === "proposée" && isPreparer && (
        <div className="stack">
          <SubmitPanel proposal={p} />
          <h2>Modifier</h2>
          <ProposalEditor
            initial={p.payload as unknown as PayloadIn}
            initialProvenance={p.provenance as Record<string, SourceRef>}
            criticalFields={p.critical_fields}
            documents={documents}
            substances={substances}
            jurisdictions={jurisdictions}
            proposalId={p.id}
            revision={p.revision}
            authorisationId={p.authorisation_id}
          />
        </div>
      )}
      {p.state === "en première validation" && !isPreparer && <FirstValidationPanel proposal={p} />}
      {p.state === "en seconde validation" && !involved && <BlindEntryPanel proposal={p} substances={substances} />}
      {p.state === "en litige" && !involved && <ArbitrationPanel proposal={p} />}
      {["en première validation", "en seconde validation", "en litige"].includes(p.state) && involved && (
        <p className="banner tone-gris">
          Vous avez déjà agi sur cette fiche : l&apos;étape suivante revient à une autre personne (RG-32).
        </p>
      )}

      {p.state !== "proposée" || !isPreparer ? (
        <section>
          <h2>Contenu</h2>
          <div className="table-scroll card" style={{ padding: 0 }}>
            <table>
              <thead>
                <tr>
                  <th>Champ critique</th>
                  <th>Valeur</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(p.critical_fields).map(([key, label]) => {
                  const value = CRITICAL_READERS[key]?.(p.payload);
                  const ref = (p.provenance as Record<string, SourceRef>)[key];
                  return (
                    <tr key={key}>
                      <td>{label}</td>
                      <td className="small">{value === null ? <em className="muted">masqué pour la ressaisie</em> : display(value)}</td>
                      <td className="small">{ref ? `doc. ${ref.document_id}, p. ${ref.page}` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {p.arbitration_reason && (
        <p>
          <strong>Arbitrage :</strong> {p.arbitration_decision} — {p.arbitration_reason}
        </p>
      )}

      <section>
        <h2>Historique</h2>
        <ol className="stack small">
          {history.map((s, i) => (
            <li key={i}>
              <strong>{s.action}</strong> par {accountLabel(s.actor)} · {s.from} → {s.to}{" "}
              <span className="muted">{new Date(s.at).toLocaleString("fr-FR")}</span>
              {Array.isArray(s.detail.corrections) && s.detail.corrections.length > 0 && (
                <ul>
                  {(s.detail.corrections as { field: string; proposed: unknown; retained: unknown }[]).map((c, k) => (
                    <li key={k}>
                      {p.critical_fields[c.field] ?? c.field} : {display(c.proposed)} → {display(c.retained)}
                    </li>
                  ))}
                </ul>
              )}
              {typeof s.detail.reason === "string" && <div className="muted">Motif : {s.detail.reason}</div>}
              {Array.isArray(s.detail.discrepancies) && s.detail.discrepancies.length > 0 && (
                <div className="muted">Discordances : {(s.detail.discrepancies as string[]).join(", ")}</div>
              )}
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}
