import { LogoMark } from "@/components/icons";
import { DEMO_ACCOUNTS, DEMO_PASSWORD } from "@/lib/accounts";
import { currentAccount } from "@/lib/api";
import { safeNext } from "@/lib/oidc";

type Props = { searchParams: Promise<{ next?: string; erreur?: string }> };

export default async function LoginPage({ searchParams }: Props) {
  const { next, erreur } = await searchParams;
  const me = await currentAccount();
  return (
    <div className="login-grid">
      <div className="card login-card">
        <LogoMark size={40} />
        <h1>Connexion</h1>
        <p className="muted" style={{ marginTop: 0 }}>
          Accédez au registre, au Copilot et au circuit de validation selon votre rôle.
        </p>
        {erreur && (
          <div className="banner tone-rouge" role="alert" style={{ marginBottom: 14 }}>
            <div>{erreur}</div>
          </div>
        )}
        {me && (
          <p>
            Connecté : <strong>{me.display_name}</strong>. Pour changer de compte, se déconnecter d&apos;abord.
          </p>
        )}
        <div className="stack">
          <a className="button" href={`/api/auth/login?next=${encodeURIComponent(safeNext(next))}`}>
            Se connecter avec Keycloak
          </a>
          {me && (
            <form method="post" action="/api/auth/logout">
              <button type="submit" className="secondary" style={{ width: "100%" }}>
                Se déconnecter
              </button>
            </form>
          )}
        </div>
        <ul className="steps">
          <li>Authentification Keycloak (OIDC, code d&apos;autorisation avec PKCE).</li>
          <li>Jetons gardés côté serveur, dans un cookie chiffré.</li>
          <li>Rôles contrôlés par l&apos;API à chaque requête.</li>
        </ul>
      </div>
      <div>
        <div className="eyebrow">Démonstration</div>
        <h2 style={{ marginTop: 0 }}>Comptes de démonstration</h2>
        <p className="muted small">
          Royaume de développement, données fictives du jeu A10. Mot de passe commun :{" "}
          <span className="mono">{DEMO_PASSWORD}</span>. Pour essayer le Copilot, prendre le professionnel vérifié.
        </p>
        <div className="table-scroll card" style={{ padding: 0 }}>
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
                <tr key={a.id} className={a.id === "cpt-03" ? "highlight" : undefined}>
                  <td className="mono small">{a.login}</td>
                  <td>{a.role}</td>
                  <td className="small">{a.hint}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
