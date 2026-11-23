"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff, describe } from "@/lib/bff";
import { CRITICAL_READERS, display, type Proposal, type Substance, WITHDRAWAL_KINDS, WITHDRAWAL_UNITS, type WithdrawalIn } from "@/lib/proposal";

function useAction() {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      await bff(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
      router.refresh();
    } catch (e) {
      setError(describe(e));
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run };
}

export function SubmitPanel({ proposal }: { proposal: Proposal }) {
  const { busy, error, run } = useAction();
  return (
    <div className="card stack">
      <h3 style={{ margin: 0 }}>Soumettre à la première validation</h3>
      {proposal.issues.length > 0 ? (
        <ul className="error">
          {proposal.issues.map((i, k) => (
            <li key={k}>{i.message}</li>
          ))}
        </ul>
      ) : (
        <p className="muted">Tous les champs critiques sont renseignés et sourcés.</p>
      )}
      {error && <p className="error">{error}</p>}
      <div>
        <button disabled={busy || proposal.issues.length > 0} onClick={() => run(`/v1/curation/proposals/${proposal.id}/submit`)}>
          Soumettre
        </button>
      </div>
    </div>
  );
}

type SourceView = { field: string; document_id: number; title: string; page: number; sha256: string | null };

/** B : chaque champ critique se confirme après affichage de sa page source (CT-VAL-01). */
export function FirstValidationPanel({ proposal }: { proposal: Proposal }) {
  const { busy, error, run } = useAction();
  const [viewed, setViewed] = useState<Record<string, SourceView>>({});
  const [confirmed, setConfirmed] = useState<Record<string, boolean>>({});
  const [reason, setReason] = useState("");
  const [viewError, setViewError] = useState<string | null>(null);
  const fields = Object.entries(proposal.critical_fields);
  const allConfirmed = fields.every(([k]) => confirmed[k]);

  async function view(field: string) {
    setViewError(null);
    try {
      const v = await bff<SourceView>(`/v1/curation/proposals/${proposal.id}/fields/${field}/source-view`, { method: "POST" });
      setViewed((s) => ({ ...s, [field]: v }));
    } catch (e) {
      setViewError(describe(e));
    }
  }

  return (
    <div className="card stack">
      <h3 style={{ margin: 0 }}>Première validation (B)</h3>
      <p className="muted small">Afficher la page source de chaque champ, comparer, puis cocher « conforme ».</p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Champ</th>
              <th>Valeur saisie</th>
              <th>Source</th>
              <th>Conforme</th>
            </tr>
          </thead>
          <tbody>
            {fields.map(([key, label]) => (
              <tr key={key}>
                <td>{label}</td>
                <td className="small">{display(CRITICAL_READERS[key]?.(proposal.payload))}</td>
                <td className="small">
                  {viewed[key] ? (
                    <span>
                      doc. n° {viewed[key].document_id}, p. {viewed[key].page}
                      <br />
                      <span className="muted">{viewed[key].title}</span>
                    </span>
                  ) : (
                    <button type="button" className="secondary" onClick={() => view(key)}>
                      Afficher la source
                    </button>
                  )}
                </td>
                <td>
                  <input
                    type="checkbox"
                    aria-label={`${label} conforme`}
                    disabled={!viewed[key]}
                    checked={!!confirmed[key]}
                    onChange={(e) => setConfirmed({ ...confirmed, [key]: e.target.checked })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {viewError && <p className="error">{viewError}</p>}
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button
          disabled={busy || !allConfirmed}
          onClick={() =>
            run(`/v1/curation/proposals/${proposal.id}/first-validation`, {
              approve: true,
              confirmed_fields: Object.keys(confirmed).filter((k) => confirmed[k]),
            })
          }
        >
          Valider
        </button>
        <label className="field" style={{ flex: "1 1 240px" }}>
          Motif du renvoi au préparateur
          <input value={reason} onChange={(e) => setReason(e.target.value)} />
        </label>
        <button className="danger" disabled={busy || !reason.trim()} onClick={() => run(`/v1/curation/proposals/${proposal.id}/first-validation`, { approve: false, reason })}>
          Renvoyer
        </button>
      </div>
    </div>
  );
}

/** C : ressaisie à l'aveugle du numéro d'AMM, des teneurs, de la posologie et des délais (RG-10). */
export function BlindEntryPanel({ proposal, substances }: { proposal: Proposal; substances: Substance[] }) {
  const { busy, error, run } = useAction();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const masked = proposal.payload as any;
  const ids: string[] = (masked?.product?.components ?? []).map((c: { substance_id: string }) => c.substance_id);
  const name = (id: string) => substances.find((s) => s.id === id)?.inn_name ?? id;
  const [maNumber, setMaNumber] = useState("");
  const [strengths, setStrengths] = useState<Record<string, string>>({});
  const [posology, setPosology] = useState("");
  const [periods, setPeriods] = useState<WithdrawalIn[]>([]);
  const setPeriod = (i: number, patch: Partial<WithdrawalIn>) => setPeriods(periods.map((w, j) => (j === i ? { ...w, ...patch } : w)));

  return (
    <div className="card stack">
      <h3 style={{ margin: 0 }}>Seconde validation à l&apos;aveugle (C)</h3>
      <p className="muted small">
        Ressaisir depuis le document source, sans voir la saisie du préparateur. Une discordance met la fiche en litige.
      </p>
      <div className="grid2">
        <label className="field">
          Numéro d&apos;AMM
          <input value={maNumber} onChange={(e) => setMaNumber(e.target.value)} />
        </label>
        {ids.map((id) => (
          <label key={id} className="field">
            Teneur de {name(id)} (telle qu&apos;écrite)
            <input value={strengths[id] ?? ""} onChange={(e) => setStrengths({ ...strengths, [id]: e.target.value })} />
          </label>
        ))}
      </div>
      <label className="field">
        Posologie
        <textarea value={posology} onChange={(e) => setPosology(e.target.value)} />
      </label>
      <h3>Délais d&apos;attente</h3>
      {periods.map((w, i) => (
        <div key={i} className="row">
          <label className="field">
            Espèce
            <input value={w.species} onChange={(e) => setPeriod(i, { species: e.target.value })} />
          </label>
          <label className="field">
            Denrée
            <input value={w.commodity} onChange={(e) => setPeriod(i, { commodity: e.target.value })} />
          </label>
          <label className="field">
            Voie
            <input value={w.route ?? ""} onChange={(e) => setPeriod(i, { route: e.target.value || null })} />
          </label>
          <label className="field">
            Nature
            <select
              value={w.kind}
              onChange={(e) => {
                const kind = e.target.value as WithdrawalIn["kind"];
                setPeriod(i, kind === "valeur" ? { kind, unit: w.unit ?? "jour" } : { kind, value: null, unit: null });
              }}
            >
              {WITHDRAWAL_KINDS.map((k) => (
                <option key={k}>{k}</option>
              ))}
            </select>
          </label>
          {w.kind === "valeur" && (
            <>
              <label className="field">
                Valeur
                <input value={w.value ?? ""} onChange={(e) => setPeriod(i, { value: e.target.value })} />
              </label>
              <label className="field">
                Unité
                <select value={w.unit ?? "jour"} onChange={(e) => setPeriod(i, { unit: e.target.value as WithdrawalIn["unit"] })}>
                  {WITHDRAWAL_UNITS.map((u) => (
                    <option key={u}>{u}</option>
                  ))}
                </select>
              </label>
            </>
          )}
        </div>
      ))}
      <div>
        <button type="button" className="secondary" onClick={() => setPeriods([...periods, { species: "", commodity: "", kind: "valeur", value: "", unit: "jour" }])}>
          Ajouter un délai
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      <div>
        <button
          disabled={busy || !maNumber.trim()}
          onClick={() =>
            run(`/v1/curation/proposals/${proposal.id}/blind-entry`, {
              ma_number: maNumber,
              components: ids.map((id) => ({ substance_id: id, strength_as_stated: strengths[id] ?? "" })),
              posology: posology || null,
              withdrawal_periods: periods,
            })
          }
        >
          Enregistrer la ressaisie
        </button>
      </div>
    </div>
  );
}

const DECISIONS = ["retenir la préparation", "retenir la ressaisie", "rejeter"] as const;

/** Arbitrage motivé par un responsable qui n'est aucun des acteurs de la fiche (RG-11). */
export function ArbitrationPanel({ proposal }: { proposal: Proposal }) {
  const { busy, error, run } = useAction();
  const [decision, setDecision] = useState<(typeof DECISIONS)[number]>("retenir la ressaisie");
  const [reason, setReason] = useState("");
  return (
    <div className="card stack">
      <h3 style={{ margin: 0 }}>Arbitrage du litige</h3>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Champ</th>
              <th>Préparation (A)</th>
              <th>Ressaisie (C)</th>
            </tr>
          </thead>
          <tbody>
            {(proposal.discrepancies ?? []).map((d, i) => (
              <tr key={i}>
                <td>{proposal.critical_fields[String(d.field)] ?? String(d.field)}</td>
                <td className="small">{display(d.prepared)}</td>
                <td className="small">{display(d.entered)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <fieldset className="row" style={{ border: 0, padding: 0 }}>
        <legend className="muted small">Décision</legend>
        {DECISIONS.map((d) => (
          <label key={d} className="row" style={{ gap: 6, alignItems: "center" }}>
            <input type="radio" name="decision" checked={decision === d} onChange={() => setDecision(d)} />
            {d}
          </label>
        ))}
      </fieldset>
      <label className="field">
        Motif (obligatoire, inscrit au journal)
        <textarea value={reason} onChange={(e) => setReason(e.target.value)} />
      </label>
      {error && <p className="error">{error}</p>}
      <div>
        <button disabled={busy || reason.trim().length < 3} onClick={() => run(`/v1/curation/proposals/${proposal.id}/arbitration`, { decision, reason })}>
          Arbitrer
        </button>
      </div>
    </div>
  );
}
