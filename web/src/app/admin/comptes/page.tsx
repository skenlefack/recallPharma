import { AccountsManager } from "@/components/admin/AccountsManager";
import { type AdminAccount, type Overview } from "@/lib/admin";
import { api, currentAccount } from "@/lib/api";

export default async function AdminAccounts() {
  const [accounts, roles, overview, me] = await Promise.all([
    api<AdminAccount[]>("/v1/admin/accounts"),
    api<string[]>("/v1/admin/roles"),
    api<Overview>("/v1/admin/overview"),
    currentAccount(),
  ]);
  return (
    <>
      <header className="admin-head">
        <div>
          <span className="section-kicker">Annuaire</span>
          <h1>Comptes et rôles</h1>
          <p className="muted">
            Les comptes sont tenus dans Keycloak ; chaque création, changement de rôle ou désactivation est tracé dans le
            journal d&apos;audit.
          </p>
        </div>
      </header>
      <AccountsManager
        initial={accounts}
        roles={roles}
        canManage={overview.permissions.includes("comptes")}
        selfId={me?.id ?? ""}
      />
    </>
  );
}
