"use client";

import Link from "next/link";
import { useState } from "react";

import { CloseIcon, PlusIcon } from "@/components/icons";
import type { AdminAlert } from "@/lib/admin";
import type { Jurisdiction } from "@/lib/api";
import { bff, describe } from "@/lib/bff";

type Props = { initial: AdminAlert[]; jurisdictions: Jurisdiction[]; canManage: boolean };

const TYPES = [
  "suspension d'AMM",
  "retrait d'AMM",
  "rappel de lot",
  "produit signalé falsifié ou sous-norme",
  "information de sécurité",
];
const LEVELS = [
  { value: "rouge", label: "Critique (rouge)" },
  { value: "orange", label: "À surveiller (orange)" },
  { value: "gris", label: "Information (gris)" },
];
const list = (v: FormDataEntryValue | null) =>
  String(v ?? "")
    .split(/[,;\s]+/)
    .map((s) => s.trim())
    .filter(Boolean);

export function AlertsManager({ initial, jurisdictions, canManage }: Props) {
  const [alerts, setAlerts] = useState(initial);
  const [creating, setCreating] = useState(false);
  const [closing, setClosing] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string } | null>(null);
  const [view, setView] = useState<"ouvertes" | "closes" | "toutes">("ouvertes");

  const shown = alerts.filter((a) => (view === "toutes" ? true : view === "closes" ? a.closed_at : !a.closed_at));

  async function publish(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const target = e.currentTarget;
    const f = new FormData(target);
    const body = {
      type: f.get("type"),
      level: f.get("level"),
      jurisdictions: f.getAll("jurisdictions").map(String),
      authorisation_ids: list(f.get("authorisation_ids")),
      batch_numbers: list(f.get("batch_numbers")),
      unlisted_product: String(f.get("unlisted_product") ?? "") || null,
      text: f.get("text"),
    };
    if (!body.jurisdictions.length) {
      setMessage({ tone: "error", text: "Choisir au moins une juridiction." });
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      const created = await bff<AdminAlert>("/v1/admin/alerts", { method: "POST", body: JSON.stringify(body) });
      setAlerts((all) => [created, ...all]);
      setCreating(false);
      target.reset();
      setMessage({ tone: "ok", text: `Alerte ${created.id} publiée.` });
    } catch (err) {
      setMessage({ tone: "error", text: describe(err) });
    } finally {
      setBusy(false);
    }
  }

  async function close(a: AdminAlert) {
    setBusy(true);
    setMessage(null);
    try {
      const closed = await bff<AdminAlert>(`/v1/admin/alerts/${a.id}/close`, { method: "POST", body: JSON.stringify({ reason }) });
      setAlerts((all) => all.map((x) => (x.id === a.id ? closed : x)));
      setClosing(null);
      setReason("");
      setMessage({ tone: "ok", text: `Alerte ${a.id} close.` });
    } catch (err) {
      setMessage({ tone: "error", text: describe(err) });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="admin-stack">
      {message && (
        <div className={`admin-flash ${message.tone}`} role="status">
          <span>{message.text}</span>
          <button type="button" className="admin-icon-btn" onClick={() => setMessage(null)} aria-label="Fermer">
            <CloseIcon size={14} />
          </button>
        </div>
      )}

      <div className="admin-toolbar">
        <div className="admin-tabs" role="tablist" aria-label="Filtrer les alertes">
          {(["ouvertes", "closes", "toutes"] as const).map((v) => (
            <button key={v} type="button" role="tab" aria-selected={view === v} onClick={() => setView(v)}>
              {v[0].toUpperCase() + v.slice(1)}
              <span>{alerts.filter((a) => (v === "toutes" ? true : v === "closes" ? a.closed_at : !a.closed_at)).length}</span>
            </button>
          ))}
        </div>
        {canManage && (
          <button type="button" id="nouvelle" className="admin-btn primary" onClick={() => setCreating((c) => !c)}>
            <PlusIcon size={16} /> Publier une alerte
          </button>
        )}
      </div>

      {creating && canManage && (
        <form className="admin-card admin-form" onSubmit={publish}>
          <h2>Nouvelle alerte</h2>
          <div className="admin-form-row">
            <label>
              Type
              <select name="type" required>
                {TYPES.map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </label>
            <label>
              Niveau
              <select name="level" required>
                {LEVELS.map((l) => (
                  <option key={l.value} value={l.value}>
                    {l.label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <fieldset className="admin-roles">
            <legend>Juridictions concernées</legend>
            {jurisdictions.map((j) => (
              <label key={j.code} className="admin-role-check">
                <input type="checkbox" name="jurisdictions" value={j.code} />
                <span>{j.name}</span>
              </label>
            ))}
          </fieldset>
          <div className="admin-form-row">
            <label>
              AMM concernées (identifiants, séparés par des virgules)
              <input name="authorisation_ids" placeholder="amm-001, amm-002" />
            </label>
            <label>
              Numéros de lot
              <input name="batch_numbers" placeholder="L27-0412" />
            </label>
          </div>
          <label>
            Produit sans AMM (falsification)
            <input name="unlisted_product" placeholder="Nom du produit signalé" />
          </label>
          <label>
            Texte publié
            <textarea name="text" required minLength={10} maxLength={2000} rows={3} placeholder="Description de l'alerte, conduite à tenir…" />
          </label>
          <div className="admin-form-actions">
            <button type="button" className="admin-btn" onClick={() => setCreating(false)}>
              Annuler
            </button>
            <button type="submit" className="admin-btn primary" disabled={busy}>
              Publier
            </button>
          </div>
        </form>
      )}

      <div className="admin-card admin-table-card">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Alerte</th>
              <th>Juridictions</th>
              <th>Publiée</th>
              <th>État</th>
              {canManage && <th className="right">Action</th>}
            </tr>
          </thead>
          <tbody>
            {shown.map((a) => (
              <tr key={a.id}>
                <td>
                  <div className="admin-alert-cell">
                    <span className={`admin-level ${a.level}`} aria-hidden />
                    <div>
                      <strong>{a.type}</strong> <span className="mono small muted">{a.id}</span>
                      <div className="small">{a.text}</div>
                      {a.authorisation_ids.length > 0 && (
                        <div className="small">
                          {a.authorisation_ids.map((id) => (
                            <Link key={id} href={`/amm/${id}`} className="admin-chip link">
                              {id}
                            </Link>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                </td>
                <td className="small">{a.jurisdictions.join(", ")}</td>
                <td className="small">{a.published_at}</td>
                <td>
                  <span className={`admin-state ${a.closed_at ? "off" : a.level === "rouge" ? "danger" : "pending"}`}>
                    {a.closed_at ? `Close le ${a.closed_at}` : "Ouverte"}
                  </span>
                </td>
                {canManage && (
                  <td className="right">
                    {!a.closed_at &&
                      (closing === a.id ? (
                        <div className="admin-close-form">
                          <input
                            value={reason}
                            onChange={(e) => setReason(e.target.value)}
                            placeholder="Motif de clôture"
                            aria-label={`Motif de clôture de ${a.id}`}
                          />
                          <button type="button" className="admin-btn primary" disabled={busy || reason.trim().length < 5} onClick={() => close(a)}>
                            Clore
                          </button>
                          <button type="button" className="admin-icon-btn" onClick={() => setClosing(null)} aria-label="Annuler">
                            <CloseIcon size={14} />
                          </button>
                        </div>
                      ) : (
                        <button type="button" className="admin-btn" onClick={() => setClosing(a.id)}>
                          Clore…
                        </button>
                      ))}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
        {shown.length === 0 && <p className="muted admin-empty">Aucune alerte dans cette vue.</p>}
      </div>
    </div>
  );
}
