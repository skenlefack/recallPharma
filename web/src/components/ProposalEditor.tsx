"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff, describe } from "@/lib/bff";
import {
  type Component,
  type DocumentOut,
  EVENT_TYPES,
  type EventIn,
  type Jurisdiction,
  type PayloadIn,
  type Proposal,
  type SourceRef,
  type Substance,
  WITHDRAWAL_KINDS,
  WITHDRAWAL_UNITS,
  type WithdrawalIn,
} from "@/lib/proposal";

type Props = {
  initial: PayloadIn;
  initialProvenance: Record<string, SourceRef>;
  criticalFields: Record<string, string>;
  documents: DocumentOut[];
  substances: Substance[];
  jurisdictions: Jurisdiction[];
  proposalId?: number;
  revision?: number;
  authorisationId?: string | null;
};

const list = (s: string) =>
  s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

/** Saisie du préparateur (A) : chaque champ critique cite son document et sa page (RG-12). */
export function ProposalEditor(props: Props) {
  const router = useRouter();
  const [p, setP] = useState<PayloadIn>(props.initial);
  const [prov, setProv] = useState<Record<string, SourceRef>>(props.initialProvenance);
  const [bulk, setBulk] = useState<SourceRef>({ document_id: props.documents[0]?.id ?? 0, page: 1 });
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const spc = p.spc ?? { languages: [], posology: "", contraindications: [], restrictions: [], withdrawal_periods: [] };

  const set = (patch: Partial<PayloadIn>) => setP({ ...p, ...patch });
  const setProduct = (patch: Partial<PayloadIn["product"]>) => set({ product: { ...p.product, ...patch } });
  const setSpc = (patch: Partial<NonNullable<PayloadIn["spc"]>>) => set({ spc: { ...spc, ...patch } });
  const setComponent = (i: number, patch: Partial<Component>) =>
    setProduct({ components: p.product.components.map((c, j) => (j === i ? { ...c, ...patch } : c)) });
  const setEvent = (i: number, patch: Partial<EventIn>) => set({ events: (p.events ?? []).map((e, j) => (j === i ? { ...e, ...patch } : e)) });
  const periods = spc.withdrawal_periods ?? [];
  const setPeriod = (i: number, patch: Partial<WithdrawalIn>) =>
    setSpc({ withdrawal_periods: periods.map((w, j) => (j === i ? { ...w, ...patch } : w)) });
  const prohibitions = (spc.restrictions ?? []).filter((r) => r.type === "interdiction");

  async function save() {
    setBusy(true);
    setError(null);
    const body = { payload: { ...p, expiry_date: p.expiry_date || null }, provenance: prov, authorisation_id: props.authorisationId ?? null };
    try {
      const saved = props.proposalId
        ? await bff<Proposal>(`/v1/curation/proposals/${props.proposalId}`, {
            method: "PUT",
            body: JSON.stringify({ ...body, expected_revision: props.revision }),
          })
        : await bff<Proposal>("/v1/curation/proposals", { method: "POST", body: JSON.stringify(body) });
      router.push(`/validation/${saved.id}`);
      router.refresh();
    } catch (e) {
      setError(describe(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      <section className="card stack">
        <h3 style={{ margin: 0 }}>AMM</h3>
        <div className="grid2">
          <label className="field">
            Juridiction
            <select value={p.jurisdiction} onChange={(e) => set({ jurisdiction: e.target.value })}>
              {props.jurisdictions.map((j) => (
                <option key={j.code} value={j.code}>
                  {j.name}
                </option>
              ))}
            </select>
          </label>
          <label className="field">
            Numéro d&apos;AMM
            <input value={p.ma_number} onChange={(e) => set({ ma_number: e.target.value })} />
          </label>
          <label className="field">
            Procédure
            <select value={p.procedure ?? "nationale"} onChange={(e) => set({ procedure: e.target.value as PayloadIn["procedure"] })}>
              <option>nationale</option>
              <option>communautaire</option>
            </select>
          </label>
          <label className="field">
            Titulaire
            <input value={p.holder} onChange={(e) => set({ holder: e.target.value })} />
          </label>
          <label className="field">
            Fabricant
            <input value={p.manufacturer ?? ""} onChange={(e) => set({ manufacturer: e.target.value || null })} />
          </label>
          <label className="field">
            Conditions de délivrance
            <input value={p.dispensing_condition ?? ""} onChange={(e) => set({ dispensing_condition: e.target.value })} />
          </label>
          <label className="field">
            Date d&apos;octroi
            <input type="date" value={p.grant_date} onChange={(e) => set({ grant_date: e.target.value })} />
          </label>
          <label className="field">
            Échéance (vide : calculée)
            <input type="date" value={p.expiry_date ?? ""} onChange={(e) => set({ expiry_date: e.target.value || null })} />
          </label>
        </div>
        <h3>Événements réglementaires</h3>
        {(p.events ?? []).map((ev, i) => (
          <div key={i} className="row">
            <label className="field">
              Type
              <select value={ev.type} onChange={(e) => setEvent(i, { type: e.target.value as EventIn["type"] })}>
                {EVENT_TYPES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </label>
            <label className="field">
              Décision
              <input type="date" value={ev.decision_date} onChange={(e) => setEvent(i, { decision_date: e.target.value })} />
            </label>
            <label className="field">
              Effet
              <input type="date" value={ev.effective_date} onChange={(e) => setEvent(i, { effective_date: e.target.value })} />
            </label>
            <label className="field" style={{ flex: "1 1 200px" }}>
              Motif
              <input value={ev.reason ?? ""} onChange={(e) => setEvent(i, { reason: e.target.value || null })} />
            </label>
          </div>
        ))}
        <div>
          <button
            type="button"
            className="secondary"
            onClick={() => set({ events: [...(p.events ?? []), { type: "octroi", decision_date: p.grant_date, effective_date: p.grant_date }] })}
          >
            Ajouter un événement
          </button>
        </div>
      </section>

      <section className="card stack">
        <h3 style={{ margin: 0 }}>Produit</h3>
        <div className="grid2">
          <label className="field">
            Dénomination
            <input value={p.product.name} onChange={(e) => setProduct({ name: e.target.value })} />
          </label>
          <label className="field">
            Désignation
            <input value={p.product.designation} onChange={(e) => setProduct({ designation: e.target.value })} />
          </label>
          <label className="field">
            Forme pharmaceutique
            <input value={p.product.pharmaceutical_form} onChange={(e) => setProduct({ pharmaceutical_form: e.target.value })} />
          </label>
          <label className="field">
            Voies (séparées par des virgules)
            <input defaultValue={(p.product.routes ?? []).join(", ")} onBlur={(e) => setProduct({ routes: list(e.target.value) })} />
          </label>
          <label className="field">
            Espèces cibles
            <input defaultValue={(p.product.target_species ?? []).join(", ")} onBlur={(e) => setProduct({ target_species: list(e.target.value) })} />
          </label>
        </div>
        <h3>Composition</h3>
        {p.product.components.map((c, i) => (
          <div key={i} className="row">
            <label className="field">
              Substance
              <select value={c.substance_id} onChange={(e) => setComponent(i, { substance_id: e.target.value })}>
                {props.substances.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.inn_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Teneur telle qu&apos;écrite
              <input value={c.strength_as_stated} onChange={(e) => setComponent(i, { strength_as_stated: e.target.value })} />
            </label>
            <label className="field">
              Valeur
              <input value={c.strength_value ?? ""} onChange={(e) => setComponent(i, { strength_value: e.target.value || null })} />
            </label>
            <label className="field">
              Unité
              <input value={c.strength_unit ?? ""} onChange={(e) => setComponent(i, { strength_unit: e.target.value || null })} />
            </label>
            <label className="field">
              Base
              <input value={c.strength_basis ?? ""} placeholder="par mL" onChange={(e) => setComponent(i, { strength_basis: e.target.value || null })} />
            </label>
          </div>
        ))}
        <div>
          <button
            type="button"
            className="secondary"
            onClick={() => setProduct({ components: [...p.product.components, { substance_id: props.substances[0]?.id ?? "", strength_as_stated: "" }] })}
          >
            Ajouter une substance
          </button>
        </div>
      </section>

      <section className="card stack">
        <h3 style={{ margin: 0 }}>RCP</h3>
        <label className="field">
          Posologie
          <textarea value={spc.posology ?? ""} onChange={(e) => setSpc({ posology: e.target.value })} />
        </label>
        <label className="field">
          Contre-indications (une par ligne ; vide = aucune)
          <textarea
            defaultValue={(spc.contraindications ?? []).join("\n")}
            onBlur={(e) => setSpc({ contraindications: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })}
          />
        </label>
        <label className="field">
          Interdictions (une par ligne : espèce ; catégorie ; texte du RCP)
          <textarea
            defaultValue={prohibitions.map((r) => [r.species, r.production_category, r.text].join(" ; ")).join("\n")}
            onBlur={(e) =>
              setSpc({
                restrictions: [
                  ...(spc.restrictions ?? []).filter((r) => r.type !== "interdiction"),
                  ...e.target.value
                    .split("\n")
                    .filter((l) => l.trim())
                    .map((l) => {
                      const [species, production_category, text] = l.split(";").map((x) => x.trim());
                      return { type: "interdiction", species, production_category, text: text ?? "" };
                    }),
                ],
              })
            }
          />
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
            <button type="button" className="danger" onClick={() => setSpc({ withdrawal_periods: periods.filter((_, j) => j !== i) })}>
              Retirer
            </button>
          </div>
        ))}
        <div>
          <button
            type="button"
            className="secondary"
            onClick={() => setSpc({ withdrawal_periods: [...periods, { species: "", commodity: "", kind: "valeur", value: "", unit: "jour" }] })}
          >
            Ajouter un délai
          </button>
        </div>
      </section>

      <section className="card stack">
        <h3 style={{ margin: 0 }}>Sources des champs critiques (document et page)</h3>
        {props.documents.length === 0 ? (
          <p className="error">
            Aucun document déposé : <Link href="/validation/documents">déposer d&apos;abord le document source</Link>.
          </p>
        ) : (
          <>
            <div className="row">
              <label className="field">
                Document
                <select value={bulk.document_id} onChange={(e) => setBulk({ ...bulk, document_id: Number(e.target.value) })}>
                  {props.documents.map((d) => (
                    <option key={d.id} value={d.id}>
                      n° {d.id} — {d.title}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Page
                <input type="number" min={1} value={bulk.page} onChange={(e) => setBulk({ ...bulk, page: Number(e.target.value) })} />
              </label>
              <button type="button" className="secondary" onClick={() => setProv(Object.fromEntries(Object.keys(props.criticalFields).map((k) => [k, { ...bulk }])))}>
                Appliquer à tous les champs
              </button>
            </div>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Champ</th>
                    <th>Document</th>
                    <th>Page</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(props.criticalFields).map(([key, label]) => (
                    <tr key={key}>
                      <td>{label}</td>
                      <td>
                        <select
                          value={prov[key]?.document_id ?? ""}
                          onChange={(e) =>
                            setProv(
                              e.target.value
                                ? { ...prov, [key]: { document_id: Number(e.target.value), page: prov[key]?.page ?? 1 } }
                                : Object.fromEntries(Object.entries(prov).filter(([k]) => k !== key)),
                            )
                          }
                        >
                          <option value="">— non cité —</option>
                          {props.documents.map((d) => (
                            <option key={d.id} value={d.id}>
                              n° {d.id}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <input
                          type="number"
                          min={1}
                          style={{ width: 80 }}
                          value={prov[key]?.page ?? ""}
                          disabled={!prov[key]}
                          onChange={(e) => setProv({ ...prov, [key]: { ...prov[key], page: Number(e.target.value) } })}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </section>

      {error && <p className="error">{error}</p>}
      <div className="row">
        <button type="button" onClick={save} disabled={busy}>
          {props.proposalId ? "Enregistrer (remet la revue à zéro)" : "Créer la proposition"}
        </button>
      </div>
    </div>
  );
}
