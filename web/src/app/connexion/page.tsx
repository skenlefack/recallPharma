import { DEMO_ACCOUNTS, DEMO_PASSWORD } from "@/lib/accounts";
import { currentAccount } from "@/lib/api";
import { safeNext } from "@/lib/oidc";

type Props = { searchParams: Promise<{ next?: string; erreur?: string }> };

export default async function LoginPage({ searchParams }: Props) {
  const { next, erreur } = await searchParams;
  const me = await currentAccount();
  return (
    <>
      <h1>Connexion</h1>
      {erreur && (
        <div className="banner tone-rouge" role="alert">
          <div>{erreur}</div>
        </div>
      )}
      {me && (
        <p>
          Connecté : <strong>{me.display_name}</strong>. Pour changer de compte, se déconnecter d&apos;abord.
        </p>
      )}
      <div className="card stack" style={{ maxWidth: 640 }}>
        <p style={{ margin: 0 }}>
          L&apos;authentification passe par Keycloak (OIDC, code d&apos;autorisation avec PKCE). Les rôles viennent de
          Keycloak et sont contrôlés par l&apos;API à chaque requête.
        </p>
        <div className="row">
          <a className="button" href={`/api/auth/login?next=${encodeURIComponent(safeNext(next))}`}>
            Se connecter avec Keycloak
          </a>
          {me && (
            <form method="post" action="/api/auth/logout">
              <button type="submit" className="secondary">
                Se déconnecter
              </button>
            </form>
          )}
        </div>
      </div>
      <h2>Comptes de démonstration</h2>
      <p className="muted small">
        Royaume de développement, données fictives du jeu A10. Mot de passe commun : <span className="mono">{DEMO_PASSWORD}</span>
      </p>
      <div className="table-scroll card" style={{ padding: 0, maxWidth: 640 }}>
        <table>
          <thead>
            <tr>
              <th>Identifiant</th>
              <th>Rôle</th>
              <th>Usage</th>
            </tr>
          </thead>
          <tbody>
            {DEMO_ACCOUNTS.map((a) => (
              <tr key={a.id}>
                <td className="mono small">{a.login}</td>
                <td>{a.role}</td>
                <td className="small">{a.hint}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
