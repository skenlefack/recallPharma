import type { Metadata } from "next";
import { Lato, Ubuntu } from "next/font/google";
import Link from "next/link";

import { LogoMark } from "@/components/icons";
import { SiteHeader } from "@/components/SiteHeader";
import { currentAccount } from "@/lib/api";

import "./globals.css";

// Polices auto-hébergées au moment de la compilation : aucun appel à Google depuis le navigateur.
const lato = Lato({ subsets: ["latin"], weight: ["300", "400", "700", "900"], variable: "--font-text" });
const ubuntu = Ubuntu({ subsets: ["latin"], weight: ["400", "500", "700"], variable: "--font-title" });

export const metadata: Metadata = {
  title: "RecallPharma",
  description: "Référentiel du médicament vétérinaire : statut, RCP, délais d'attente et alertes, avec leurs preuves.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const me = await currentAccount();
  return (
    <html lang="fr" className={`${lato.variable} ${ubuntu.variable}`}>
      <body>
        <SiteHeader me={me ? { display_name: me.display_name, roles: me.roles } : null} />
        <main>
          <div className="wrap">{children}</div>
        </main>
        <footer className="site-footer">
          <div className="wrap footer-grid">
            <div>
              <span className="footer-brand">
                <LogoMark size={26} /> RecallPharma
              </span>
              <p>
                Référentiel du médicament vétérinaire : statut des AMM, texte des RCP, délais d&apos;attente et alertes,
                chaque information avec sa preuve.
              </p>
            </div>
            <div>
              <h4>Consulter</h4>
              <Link href="/">Recherche</Link>
              <Link href="/alertes">Alertes</Link>
              <Link href="/copilote">Copilot</Link>
            </div>
            <div>
              <h4>Équipes</h4>
              <Link href="/validation">Validation des données</Link>
              <Link href="/validation/documents">Documents sources</Link>
              <Link href="/connexion">Connexion</Link>
            </div>
            <div>
              <h4>Avertissement</h4>
              <p>
                Prototype sur données entièrement fictives (jeu A10). RecallPharma ne remplace pas le jugement clinique et
                n&apos;est pas informé systématiquement des suspensions et des rappels.
              </p>
            </div>
          </div>
          <div className="footer-bottom">
            <div className="wrap">© {new Date().getFullYear()} RecallPharma · intégré à RecallVET</div>
          </div>
        </footer>
      </body>
    </html>
  );
}
