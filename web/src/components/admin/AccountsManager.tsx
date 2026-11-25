"use client";

import { useMemo, useState } from "react";

import { CheckShieldIcon, CloseIcon, KeyIcon, PlusIcon, PowerIcon, SearchIcon, UsersIcon } from "@/components/icons";
import type { AdminAccount } from "@/lib/admin";
import { bff, describe } from "@/lib/bff";

type Props = { initial: AdminAccount[]; roles: string[]; canManage: boolean; selfId: string };

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter((w) => /^\p{L}/u.test(w))
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

export function AccountsManager({ initial, roles, canManage, selfId }: Props) {
  const [accounts, setAccounts] = useState(initial);
  const [filter, setFilter] = useState("");
  const [role, setRole] = useState("");
  const [editing, setEditing] = useState<string | null>(null);
  const [draftRoles, setDraftRoles] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "error"; text: string; secret?: string } | null>(null);
  const [creating, setCreating] = useState(false);

  const shown = useMemo(() => {
    const f = filter.trim().toLowerCase();
    return accounts.filter(
      (a) =>
        (!f || a.display_name.toLowerCase().includes(f) || a.login.includes(f) || a.id.includes(f)) &&
        (!role || a.roles.includes(role)),
    );
  }, [accounts, filter, role]);

  const replace = (a: AdminAccount) => setAccounts((all) => all.map((x) => (x.id === a.id ? a : x)));

  async function run<T>(action: () => Promise<T>, ok: (r: T) => void) {
    setBusy(true);
    setMessage(null);
    try {
      ok(await action());
    } catch (e) {
      setMessage({ tone: "error", text: describe(e) });
    } finally {
      setBusy(false);
    }
  }

  const saveRoles = (a: AdminAccount) =>
    run(
      () => bff<AdminAccount>(`/v1/admin/accounts/${a.id}/roles`, { method: "PUT", body: JSON.stringify({ roles: draftRoles }) }),
      (r) => {
        replace(r);
        setEditing(null);
        setMessage({ tone: "ok", text: `Rôles de ${r.display_name} mis à jour.` });
      },
    );

  const toggle = (a: AdminAccount) =>
    run(
      () => bff<AdminAccount>(`/v1/admin/accounts/${a.id}/active`, { method: "POST", body: JSON.stringify({ active: !a.active }) }),
      (r) => {
        replace(r);
        setMessage({ tone: "ok", text: `${r.display_name} : compte ${r.active ? "réactivé" : "désactivé (sessions fermées)"}.` });
      },
    );

  const resetMfa = (a: AdminAccount) =>
    run(
      () => bff<AdminAccount>(`/v1/admin/accounts/${a.id}/mfa-reset`, { method: "POST" }),
      (r) => {
        replace(r);
        setMessage({ tone: "ok", text: `Double authentification de ${r.display_name} retirée : à réactiver par l'utilisateur.` });
      },
    );

  const reset = (a: AdminAccount) =>
    run(
      () => bff<{ temporary_password: string }>(`/v1/admin/accounts/${a.id}/password-reset`, { method: "POST" }),
      (r) =>
        setMessage({
          tone: "ok",
          text: `Nouveau mot de passe provisoire de ${a.display_name}, à transmettre par un canal sûr :`,
          secret: r.temporary_password,
        }),
    );

  async function create(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    const body = {
      login: String(form.get("login")),
      display_name: String(form.get("display_name")),
      roles: form.getAll("roles").map(String),
    };
    if (!body.roles.length) {
      setMessage({ tone: "error", text: "Choisir au moins un rôle." });
      return;
    }
    const target = e.currentTarget;
    await run(
      () => bff<AdminAccount & { temporary_password: string }>("/v1/admin/accounts", { method: "POST", body: JSON.stringify(body) }),
      (r) => {
        setAccounts((all) => [...all, r]);
        setCreating(false);
        target.reset();
        setMessage({
          tone: "ok",
          text: `Compte ${r.id} créé pour ${r.display_name}. Mot de passe provisoire, affiché une seule fois :`,
          secret: r.temporary_password,
        });
      },
    );
  }

  return (
    <div className="admin-stack">
      {message && (
        <div className={`admin-flash ${message.tone}`} role="status">
          <span>{message.text}</span>
          {message.secret && <code className="admin-secret">{message.secret}</code>}
          <button type="button" className="admin-icon-btn" onClick={() => setMessage(null)} aria-label="Fermer">
            <CloseIcon size={14} />
          </button>
        </div>
      )}

      <div className="admin-toolbar">
        <label className="admin-search">
          <SearchIcon size={16} />
          <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Nom, e-mail ou identifiant" aria-label="Filtrer les comptes" />
        </label>
        <select value={role} onChange={(e) => setRole(e.target.value)} aria-label="Filtrer par rôle" className="admin-select">
          <option value="">Tous les rôles</option>
          {roles.map((r) => (
            <option key={r}>{r}</option>
          ))}
        </select>
        <span className="muted small">
          {shown.length} compte{shown.length > 1 ? "s" : ""}
        </span>
        {canManage && (
          <button type="button" id="nouveau" className="admin-btn primary" onClick={() => setCreating((v) => !v)}>
            <PlusIcon size={16} /> Nouveau compte
          </button>
        )}
      </div>

      {creating && canManage && (
        <form className="admin-card admin-form" onSubmit={create}>
          <h2>Nouveau compte</h2>
          <div className="admin-form-row">
            <label>
              Nom affiché
              <input name="display_name" required minLength={2} placeholder="Prénom Nom" />
            </label>
            <label>
              Adresse e-mail (identifiant)
              <input name="login" type="email" required placeholder="nom@organisation.fr" />
            </label>
          </div>
          <fieldset className="admin-roles">
            <legend>Rôles</legend>
            {roles.map((r) => (
              <label key={r} className="admin-role-check">
                <input type="checkbox" name="roles" value={r} />
                <span>{r}</span>
              </label>
            ))}
          </fieldset>
          <p className="small muted">Un mot de passe provisoire est généré et affiché une seule fois après la création.</p>
          <div className="admin-form-actions">
            <button type="button" className="admin-btn" onClick={() => setCreating(false)}>
              Annuler
            </button>
            <button type="submit" className="admin-btn primary" disabled={busy}>
              Créer le compte
            </button>
          </div>
        </form>
      )}

      <div className="admin-card admin-table-card">
        <table className="admin-table">
          <thead>
            <tr>
              <th>Compte</th>
              <th>Rôles</th>
              <th>État</th>
              {canManage && <th className="right">Actions</th>}
            </tr>
          </thead>
          <tbody>
            {shown.map((a) => (
              <tr key={a.id} className={a.active ? undefined : "inactive"}>
                <td>
                  <div className="admin-person">
                    <span className="admin-avatar" aria-hidden>
                      {initials(a.display_name)}
                    </span>
                    <div>
                      <strong>{a.display_name}</strong>
                      <span className="small muted">
                        {a.login} · <span className="mono">{a.id}</span>
                        {a.id === selfId && " · vous"}
                      </span>
                    </div>
                  </div>
                </td>
                <td>
                  {editing === a.id ? (
                    <div className="admin-roles inline">
                      {roles.map((r) => (
                        <label key={r} className="admin-role-check">
                          <input
                            type="checkbox"
                            checked={draftRoles.includes(r)}
                            onChange={(e) =>
                              setDraftRoles((d) => (e.target.checked ? [...d, r] : d.filter((x) => x !== r)))
                            }
                          />
                          <span>{r}</span>
                        </label>
                      ))}
                      <div className="admin-form-actions">
                        <button type="button" className="admin-btn" onClick={() => setEditing(null)}>
                          Annuler
                        </button>
                        <button type="button" className="admin-btn primary" disabled={busy || !draftRoles.length} onClick={() => saveRoles(a)}>
                          Enregistrer
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="admin-chips">
                      {a.roles.map((r) => (
                        <span key={r} className="admin-chip">
                          {r}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td>
                  <span className={`admin-state ${a.active ? "on" : "off"}`}>{a.active ? "Actif" : "Désactivé"}</span>
                  {a.mfa_enabled && (
                    <span className="admin-state mfa" title="Double authentification active">
                      2FA
                    </span>
                  )}
                </td>
                {canManage && (
                  <td className="right">
                    <div className="admin-row-actions">
                      <button
                        type="button"
                        className="admin-icon-btn"
                        title="Modifier les rôles"
                        aria-label={`Modifier les rôles de ${a.display_name}`}
                        disabled={busy}
                        onClick={() => {
                          setEditing(a.id);
                          setDraftRoles(a.roles);
                        }}
                      >
                        <UsersIcon size={16} />
                      </button>
                      <button
                        type="button"
                        className="admin-icon-btn"
                        title="Réinitialiser le mot de passe"
                        aria-label={`Réinitialiser le mot de passe de ${a.display_name}`}
                        disabled={busy}
                        onClick={() => reset(a)}
                      >
                        <KeyIcon size={16} />
                      </button>
                      {a.mfa_enabled && (
                        <button
                          type="button"
                          className="admin-icon-btn"
                          title="Réinitialiser la double authentification (téléphone perdu)"
                          aria-label={`Réinitialiser la double authentification de ${a.display_name}`}
                          disabled={busy}
                          onClick={() => resetMfa(a)}
                        >
                          <CheckShieldIcon size={16} />
                        </button>
                      )}
                      <button
                        type="button"
                        className={`admin-icon-btn ${a.active ? "danger" : "ok"}`}
                        title={a.active ? "Désactiver" : "Réactiver"}
                        aria-label={`${a.active ? "Désactiver" : "Réactiver"} ${a.display_name}`}
                        disabled={busy || a.id === selfId}
                        onClick={() => toggle(a)}
                      >
                        <PowerIcon size={16} />
                      </button>
                    </div>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
