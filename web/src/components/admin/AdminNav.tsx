"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BellIcon, ChatIcon, GridIcon, HistoryIcon, PillIcon, UsersIcon } from "@/components/icons";

const LINKS = [
  { href: "/admin", label: "Tableau de bord", icon: GridIcon, exact: true },
  { href: "/admin/comptes", label: "Comptes et rôles", icon: UsersIcon },
  { href: "/admin/amm", label: "AMM", icon: PillIcon },
  { href: "/admin/alertes", label: "Alertes", icon: BellIcon },
  { href: "/admin/copilot", label: "Copilot", icon: ChatIcon },
  { href: "/admin/journal", label: "Journal d'audit", icon: HistoryIcon },
];

export function AdminNav() {
  const path = usePathname() ?? "/admin";
  return (
    <nav className="admin-nav" aria-label="Administration">
      {LINKS.map(({ href, label, icon: Icon, exact }) => {
        const current = exact ? path === href : path.startsWith(href);
        return (
          <Link key={href} href={href} aria-current={current ? "page" : undefined}>
            <span className="admin-nav-icon">
              <Icon size={18} />
            </span>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
