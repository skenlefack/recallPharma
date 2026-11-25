import { redirect } from "next/navigation";

import { MfaManager } from "@/components/MfaManager";
import { currentAccount } from "@/lib/api";

export const metadata = { title: "Sécurité du compte · RecallPharma" };

export default async function SecurityPage() {
  const me = await currentAccount();
  if (!me) redirect("/connexion?next=/compte/securite");
  return (
    <div className="account-page">
      <div className="section-title account-title">
        <span className="section-kicker">Mon compte</span>
        <h1>Sécurité du compte</h1>
        <p>
          {me.display_name} · {me.roles.join(", ")}
        </p>
      </div>
      <section className="admin-card account-card">
        <h2>Double authentification</h2>
        <MfaManager enabled={me.mfa_enabled ?? false} />
      </section>
    </div>
  );
}
