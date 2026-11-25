"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { AppNav } from "@/components/AppNav";
import { LogoutIcon } from "@/components/icons";
import { Logo } from "@/components/Logo";

type Me = { display_name: string; roles: string[] } | null;

const initials = (name: string) =>
  name
    .replace(/\(.*\)/, "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");

/** En-tête : transparent sur l'image d'accueil, plein dès qu'on défile ou sur les autres pages. */
export function SiteHeader({ me }: { me: Me }) {
  const path = usePathname() ?? "/";
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);
  const overlay = path === "/" && !scrolled;
  return (
    <header className={`top${overlay ? " overlay" : ""}`}>
      <div className="demo-ribbon" role="note">
        Données entièrement fictives (jeu A10) · prototype de démonstration
      </div>
      <div className="wrap">
        <Link href="/" className="brand" aria-label="RecallPharma, accueil">
          <Logo variant="sombre" height={50} />
        </Link>
        <AppNav />
        <div className="who">
          {me ? (
            <form method="post" action="/api/auth/logout" className="user-chip">
              <span className="avatar" aria-hidden>
                {initials(me.display_name)}
              </span>
              <span className="user-text">
                <span className="user-name">{me.display_name}</span>
                <span className="user-role">{me.roles.join(", ")}</span>
              </span>
              <button type="submit" className="icon-button" title="Se déconnecter" aria-label="Se déconnecter">
                <LogoutIcon size={17} />
              </button>
            </form>
          ) : (
            <Link href="/connexion" className="button pill">
              Se connecter
            </Link>
          )}
        </div>
      </div>
    </header>
  );
}
