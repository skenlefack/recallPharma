import Link from "next/link";
import { redirect } from "next/navigation";

import { AdminNav } from "@/components/admin/AdminNav";
import { CogIcon, LockIcon } from "@/components/icons";
import { canAdmin } from "@/lib/admin";
import { currentAccount } from "@/lib/api";

export const metadata = { title: "Administration · RecallPharma" };

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const me = await currentAccount();
  if (!me) redirect("/connexion?next=/admin");
  if (!canAdmin(me)) {
    return (
      <div className="copilot-locked">
        <span className="copilot-locked-icon" aria-hidden>
          <LockIcon size={30} />
        </span>
        <h2>Administration réservée</h2>
        <p>
          L&apos;espace d&apos;administration est ouvert aux administrateurs, aux auditeurs et à l&apos;évaluateur de
          pharmacovigilance. Votre compte : {me.roles.join(", ")}.
        </p>
        <Link href="/" className="button pill">
          Retour à l&apos;accueil
        </Link>
      </div>
    );
  }
  return (
    <div className="admin full-bleed">
      <aside className="admin-side">
        <div className="admin-side-head">
          <span className="admin-side-badge" aria-hidden>
            <CogIcon size={20} />
          </span>
          <div>
            <strong>Administration</strong>
            <span>{me.display_name}</span>
          </div>
        </div>
        <AdminNav />
        <div className="admin-side-roles">
          {me.roles.map((r) => (
            <span key={r}>{r}</span>
          ))}
        </div>
      </aside>
      <div className="admin-main">{children}</div>
    </div>
  );
}
