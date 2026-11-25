import type { Metadata } from "next";
import { Lato, Ubuntu } from "next/font/google";

import { SiteFooter } from "@/components/SiteFooter";
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
      <body id="top">
        <SiteHeader
          me={
            me
              ? {
                  display_name: me.display_name,
                  roles: me.roles,
                  mfa_pending: Boolean(me.mfa_required && !me.mfa_enabled),
                }
              : null
          }
        />
        <main>
          <div className="wrap">{children}</div>
        </main>
        <SiteFooter />
      </body>
    </html>
  );
}
