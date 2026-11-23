import { DEMO_ACCOUNTS } from "@/lib/accounts";
import { currentUser } from "@/lib/api";

type Props = { searchParams: Promise<{ next?: string }> };

export default async function LoginPage({ searchParams }: Props) {
  const { next = "/validation" } = await searchParams;
  const user = await currentUser();
  return (
    <>
      <h1>Connexion de démonstration</h1>
      <p className="muted">
        Choisir un compte fictif du jeu A10. En production, la connexion passera par Keycloak (OIDC, double facteur).
      </p>
      <form method="post" action="/api/session" className="card stack" style={{ maxWidth: 560 }}>
        <input type="hidden" name="next" value={next.startsWith("/") ? next : "/validation"} />
        {DEMO_ACCOUNTS.map((a) => (
          <label key={a.id} className="row" style={{ alignItems: "center", gap: 8 }}>
            <input type="radio" name="account" value={a.id} defaultChecked={a.id === (user ?? "cpt-06")} />
            <span>
              <strong>{a.role}</strong> <span className="mono small">{a.id}</span>
              <span className="muted small"> — {a.hint}</span>
            </span>
          </label>
        ))}
        <div className="row">
          <button type="submit">Se connecter</button>
        </div>
      </form>
    </>
  );
}
