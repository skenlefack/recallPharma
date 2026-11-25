import { redirect } from "next/navigation";

import { MfaManager } from "@/components/MfaManager";
import { currentAccount } from "@/lib/api";
import { safeNext } from "@/lib/oidc";

export const metadata = { title: "Sécurité du compte · RecallPharma" };

type Props = { searchParams: Promise<{ obligatoire?: string; next?: string }> };

export default async function SecurityPage({ searchParams }: Props) {
  const { next } = await searchParams;
  const me = await currentAccount();
  if (!me) redirect("/connexion?next=/compte/securite");
  const required = me.mfa_required ?? false;
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
        <MfaManager
          enabled={me.mfa_enabled ?? false}
          required={required}
          next={next ? safeNext(next) : undefined}
        />
      </section>
    </div>
  );
}
