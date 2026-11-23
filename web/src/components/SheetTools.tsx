"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { bff, BffError, describe } from "@/lib/bff";
import type { components } from "@/lib/api-types";

type Withdrawal = components["schemas"]["WithdrawalOut"];
type WithdrawalResponse = components["schemas"]["WithdrawalResponse"];
type BatchCheck = components["schemas"]["BatchCheckResponse"];

/** Fin du délai d'attente (RG-21) : formule affichée ; plusieurs délais possibles → choisir la voie. */
export function WithdrawalCalculator({ authorisationId, periods }: { authorisationId: string; periods: Withdrawal[] }) {
  const species = [...new Set(periods.map((p) => p.species))];
  const [form, setForm] = useState({
    species: species[0] ?? "",
    commodity: periods[0]?.commodity ?? "",
    route: "",
    when: "",
    water: "",
  });
  const [result, setResult] = useState<WithdrawalResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const commodities = [...new Set(periods.filter((p) => p.species === form.species).map((p) => p.commodity))];
  const routes = [...new Set(periods.filter((p) => p.species === form.species && p.route).map((p) => p.route!))];
  const needsWater = periods.some((p) => p.species === form.species && p.commodity === form.commodity && p.unit === "degré-jour");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setResult(null);
    try {
      // L'heure saisie est celle du navigateur ; elle part avec son décalage, l'API la convertit au fuseau légal.
      const when = new Date(form.when);
      setResult(
        await bff<WithdrawalResponse>(`/v1/authorisations/${authorisationId}/withdrawal-end`, {
          method: "POST",
          body: JSON.stringify({
            species: form.species,
            commodity: form.commodity,
            route: form.route || null,
            last_administration: when.toISOString(),
            water_temperature_c: form.water || null,
          }),
        }),
      );
    } catch (err) {
      if (err instanceof BffError && err.status === 409) setError("Plusieurs délais correspondent : préciser la voie.");
      else setError(describe(err));
    }
  }

  return (
    <form className="card stack" onSubmit={submit}>
      <h3 style={{ margin: 0 }}>Calculer la fin du délai d&apos;attente</h3>
      <div className="grid2">
        <label className="field">
          Espèce
          <select value={form.species} onChange={(e) => setForm({ ...form, species: e.target.value, commodity: "" })}>
            {species.map((s) => (
              <option key={s}>{s}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Denrée
          <select value={form.commodity} onChange={(e) => setForm({ ...form, commodity: e.target.value })} required>
            <option value="">—</option>
            {commodities.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Voie
          <select value={form.route} onChange={(e) => setForm({ ...form, route: e.target.value })}>
            <option value="">non précisée</option>
            {routes.map((r) => (
              <option key={r}>{r}</option>
            ))}
          </select>
        </label>
        <label className="field">
          Dernière administration
          <input type="datetime-local" value={form.when} onChange={(e) => setForm({ ...form, when: e.target.value })} required />
        </label>
        {needsWater && (
          <label className="field">
            Température moyenne de l&apos;eau (°C)
            <input type="number" min="0.1" step="0.1" value={form.water} onChange={(e) => setForm({ ...form, water: e.target.value })} />
          </label>
        )}
      </div>
      <div>
        <button type="submit">Calculer</button>
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <div className={`banner ${result.outcome === "calculé" ? "tone-vert" : result.outcome === "usage interdit" ? "tone-rouge" : "tone-gris"}`}>
          <div>
            <strong>{result.message}</strong>
            {result.formula && <div className="small mono">{result.formula}</div>}
            <div className="small">Fuseau légal : {result.timezone}</div>
          </div>
        </div>
      )}
    </form>
  );
}

/** RG-22 : deux réponses possibles, jamais « authentique ». */
export function BatchCheckForm({ authorisationId }: { authorisationId: string }) {
  const [batch, setBatch] = useState("");
  const [result, setResult] = useState<BatchCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      setResult(
        await bff<BatchCheck>("/v1/batch-check", {
          method: "POST",
          body: JSON.stringify({ authorisation_id: authorisationId, batch_number: batch }),
        }),
      );
    } catch (err) {
      setError(describe(err));
    }
  }
  return (
    <form className="card stack" onSubmit={submit}>
      <h3 style={{ margin: 0 }}>Vérifier un numéro de lot</h3>
      <div className="row">
        <label className="field" style={{ flex: "1 1 200px" }}>
          Numéro de lot
          <input value={batch} onChange={(e) => setBatch(e.target.value)} required maxLength={64} />
        </label>
        <button type="submit">Vérifier</button>
      </div>
      {error && <p className="error">{error}</p>}
      {result && (
        <div className={`banner ${result.alert_ids.length ? "tone-rouge" : "tone-gris"}`}>
          <div>
            <strong>{result.answer}</strong>
            {result.alert_ids.length > 0 && <span> (alerte {result.alert_ids.join(", ")})</span>}
            <div className="small">{result.notice}</div>
          </div>
        </div>
      )}
    </form>
  );
}

export function ProposeUpdateButton({ authorisationId }: { authorisationId: string }) {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  async function start() {
    try {
      const p = await bff<{ id: number }>(`/v1/curation/authorisations/${authorisationId}/proposals`, { method: "POST" });
      router.push(`/validation/${p.id}`);
    } catch (err) {
      setError(err instanceof BffError && err.status === 401 ? "Se connecter avec un compte de validation." : describe(err));
    }
  }
  return (
    <span>
      <button className="secondary" onClick={start} type="button">
        Proposer une mise à jour
      </button>
      {error && <span className="error small"> {error}</span>}
    </span>
  );
}
