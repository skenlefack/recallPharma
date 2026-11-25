import Link from "next/link";

import { AlertTriangleIcon, ArrowRightIcon, BellIcon, ChatIcon, CheckShieldIcon, KeyIcon, MailIcon } from "@/components/icons";
import { Logo } from "@/components/Logo";
import { PasswordField } from "@/components/PasswordField";
import { currentAccount } from "@/lib/api";
import { IMAGES } from "@/lib/images";
import { safeNext } from "@/lib/oidc";

type Props = { searchParams: Promise<{ next?: string; erreur?: string; identifiant?: string; etape?: string }> };

const POINTS = [
  { icon: CheckShieldIcon, text: "Chaque information avec son niveau de preuve et sa source" },
  { icon: BellIcon, text: "Alertes, suspensions et rappels de lots suivis" },
  { icon: ChatIcon, text: "Copilot contrôlé pour les professionnels vérifiés" },
];

export default async function LoginPage({ searchParams }: Props) {
  const { next, erreur, identifiant, etape } = await searchParams;
  const me = await currentAccount();
  return (
    <div className="auth">
      <aside className="auth-visual" style={{ backgroundImage: `url(${IMAGES.hero})` }}>
        <div className="auth-visual-inner">
          <Logo variant="sombre" height={56} />
          <h2>Le référentiel du médicament vétérinaire, avec sa preuve.</h2>
          <ul>
            {POINTS.map(({ icon: Icon, text }) => (
              <li key={text}>
                <span aria-hidden>
                  <Icon size={18} />
                </span>
                {text}
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <section className="auth-panel">
        {me ? (
          <div className="auth-signed">
            <span className="auth-avatar" aria-hidden>
              {me.display_name.slice(0, 1)}
            </span>
            <h1>Vous êtes connecté</h1>
            <p className="muted">
              {me.display_name} · {me.roles.join(", ")}
            </p>
            <Link href={safeNext(next)} className="auth-submit">
              Continuer <ArrowRightIcon size={16} />
            </Link>
            <form method="post" action="/api/auth/logout">
              <button type="submit" className="auth-secondary">
                Changer de compte
              </button>
            </form>
          </div>
        ) : etape === "code" ? (
          <form method="post" action="/api/auth/mfa" className="auth-form">
            <span className="section-kicker">Double authentification</span>
            <h1>Code de vérification</h1>
            <p className="muted">
              Saisissez le code à 6 chiffres affiché par votre application d&apos;authentification (FreeOTP, Google
              Authenticator, Microsoft Authenticator…).
            </p>
            {erreur && (
              <div className="auth-error" role="alert">
                <AlertTriangleIcon size={18} />
                <span>{erreur}</span>
              </div>
            )}
            <label htmlFor="code">Code à 6 chiffres</label>
            <div className="auth-input auth-code">
              <KeyIcon size={18} />
              <input
                id="code"
                name="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                pattern="[0-9 ]{6,7}"
                maxLength={7}
                placeholder="123 456"
                autoFocus
                required
              />
            </div>
            <button type="submit" className="auth-submit">
              Vérifier <ArrowRightIcon size={16} />
            </button>
            <p className="auth-help">
              Le code change toutes les 30 secondes. Téléphone perdu ? Votre administrateur peut réinitialiser la double
              authentification. <Link href={`/connexion${next ? `?next=${encodeURIComponent(next)}` : ""}`}>Recommencer la connexion</Link>
            </p>
          </form>
        ) : (
          <form method="post" action="/api/auth/login" className="auth-form">
            <span className="section-kicker">Espace professionnel</span>
            <h1>Connexion</h1>
            <p className="muted">Accédez au registre, au Copilot et au circuit de validation selon votre rôle.</p>
            {erreur && (
              <div className="auth-error" role="alert">
                <AlertTriangleIcon size={18} />
                <span>{erreur}</span>
              </div>
            )}
            <input type="hidden" name="next" value={safeNext(next)} />
            <label htmlFor="username">Adresse e-mail</label>
            <div className="auth-input">
              <MailIcon size={18} />
              <input
                id="username"
                name="username"
                type="email"
                autoComplete="username"
                placeholder="nom@exemple.fr"
                defaultValue={identifiant}
                autoFocus={!identifiant}
                required
              />
            </div>
            <label htmlFor="password">Mot de passe</label>
            <PasswordField />
            <button type="submit" className="auth-submit">
              Se connecter <ArrowRightIcon size={16} />
            </button>
            <p className="auth-help">
              Mot de passe oublié ou compte bloqué ? Contactez l&apos;administrateur de votre organisation. Après plusieurs
              échecs, le compte est verrouillé temporairement.
            </p>
          </form>
        )}
      </section>
    </div>
  );
}
