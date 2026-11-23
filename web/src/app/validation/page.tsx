import Link from "next/link";
import { redirect } from "next/navigation";

import { type Proposal, api, currentAccount } from "@/lib/api";
import { CRITICAL_READERS, STATE_TONE, display } from "@/lib/proposal";

const STATES = ["proposée", "en première validation", "en seconde validation", "en litige", "publiée", "archivée"];

export default async function ValidationPage() {
  const me = await currentAccount();
  if (!me) redirect("/connexion?next=/validation");
  const user = me.id;
  const proposals = await api<Proposal[]>("/v1/curation/proposals");
  return (
    <>
      <h1>Validation des données</h1>
      <p className="muted">
        Circuit A → B → C : préparation, validation champ par champ, ressaisie à l&apos;aveugle. Connecté :{" "}
        {me.display_name} ({me.roles.join(", ")}).
      </p>
      {!me.can_curate && (
        <div className="banner tone-orange" role="status">
          <div>
            Ce compte ne peut ni préparer ni valider : il faut le rôle Validateur ou Responsable réglementaire, jamais
            celui d&apos;administrateur technique (RG-32). Les rôles se gèrent dans Keycloak.
          </div>
        </div>
      )}
      <div className="row">
        <Link className="button" href="/validation/nouvelle">
          Nouvelle proposition
        </Link>
        <Link className="button secondary" href="/validation/documents">
          Documents sources
        </Link>
      </div>
      {STATES.map((state) => {
        const items = proposals.filter((p) => p.state === state);
        if (!items.length) return null;
        return (
          <section key={state}>
            <h2>
              <span className={`badge tone-${STATE_TONE[state]}`}>{state}</span> <span className="muted small">{items.length}</span>
            </h2>
            <div className="table-scroll card" style={{ padding: 0 }}>
              <table>
                <thead>
                  <tr>
                    <th>N°</th>
                    <th>AMM</th>
                    <th>Produit</th>
                    <th>Origine</th>
                    <th>À faire</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((p) => (
                    <tr key={p.id}>
                      <td>
                        <Link href={`/validation/${p.id}`}>#{p.id}</Link>
                      </td>
                      <td className="mono small">{display(CRITICAL_READERS.ma_number(p.payload)).replace("—", "masqué")}</td>
                      <td>{display(CRITICAL_READERS.denomination(p.payload))}</td>
                      <td className="small">{p.origin}</td>
                      <td className="small">{nextStep(p, user)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}
      {proposals.length === 0 && <p className="muted">Aucune proposition pour l&apos;instant.</p>}
    </>
  );
}

function nextStep(p: Proposal, user: string): string {
  switch (p.state) {
    case "proposée":
      return p.prepared_by === user ? "Compléter et soumettre" : `Préparation par ${p.prepared_by}`;
    case "en première validation":
      return p.prepared_by === user ? "Attente d'un premier validateur" : "Valider (B)";
    case "en seconde validation":
      return [p.prepared_by, p.first_validator].includes(user) ? "Attente d'un second validateur" : "Ressaisir à l'aveugle (C)";
    case "en litige":
      return [p.prepared_by, p.first_validator, p.second_validator].includes(user) ? "Attente d'un arbitre" : "Arbitrer";
    default:
      return "—";
  }
}
