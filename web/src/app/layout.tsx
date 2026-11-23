import type { Metadata } from "next";
import Link from "next/link";

import { currentAccount } from "@/lib/api";

import "./globals.css";

export const metadata: Metadata = {
  title: "RecallPharma",
  description: "Référentiel du médicament vétérinaire : statut, RCP, délais d'attente et alertes, avec leurs preuves.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const me = await currentAccount();
  return (
    <html lang="fr">
      <body>
        <header className="top">
          <div className="wrap">
            <Link href="/" className="brand">
              RecallPharma
            </Link>
            <nav aria-label="Navigation principale">
              <Link href="/">Recherche</Link>
              <Link href="/alertes">Alertes</Link>
              <Link href="/validation">Validation</Link>
            </nav>
            <span className="who">
              {me ? (
                <form method="post" action="/api/auth/logout" className="inline">
                  {me.display_name} ·{" "}
                  <button type="submit" className="link">
                    se déconnecter
                  </button>
                </form>
              ) : (
                <Link href="/connexion">Se connecter</Link>
              )}
            </span>
          </div>
        </header>
        <main>
          <div className="wrap">{children}</div>
        </main>
        <footer className="legal">
          <div className="wrap">
            Prototype sur données entièrement fictives (jeu A10). RecallPharma ne remplace pas le jugement
            clinique et n&apos;est pas informé systématiquement des suspensions et des rappels.
          </div>
        </footer>
      </body>
    </html>
  );
}
