"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { BellIcon, ChatIcon, CheckShieldIcon, SearchIcon } from "@/components/icons";

const LINKS = [
  { href: "/", label: "Recherche", icon: SearchIcon, match: (p: string) => p === "/" || p.startsWith("/amm") },
  { href: "/alertes", label: "Alertes", icon: BellIcon, match: (p: string) => p.startsWith("/alertes") },
  { href: "/copilote", label: "Copilot", icon: ChatIcon, match: (p: string) => p.startsWith("/copilote") },
  { href: "/validation", label: "Validation", icon: CheckShieldIcon, match: (p: string) => p.startsWith("/validation") },
];

/** Navigation principale : la page courante est marquée (aria-current), pas seulement colorée. */
export function AppNav() {
  const path = usePathname() ?? "/";
  return (
    <nav aria-label="Navigation principale" className="app-nav">
      {LINKS.map(({ href, label, icon: Icon, match }) => (
        <Link key={href} href={href} aria-current={match(path) ? "page" : undefined}>
          <Icon size={17} />
          <span>{label}</span>
        </Link>
      ))}
    </nav>
  );
}
