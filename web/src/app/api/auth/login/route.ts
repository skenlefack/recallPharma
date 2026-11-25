import { type NextRequest, NextResponse } from "next/server";

import { API_URL } from "@/lib/api";
import {
  LoginError,
  MFA_COOKIE,
  type PendingMfa,
  SESSION_COOKIE,
  cookieOptions,
  passwordLogin,
  safeNext,
  seal,
  siteUrl,
} from "@/lib/oidc";

/**
 * Formulaire de connexion du site (POST, même origine) : identifiant et mot de passe vérifiés par Keycloak côté serveur.
 * Si le compte a activé la double authentification, les jetons restent dans un cookie scellé de 5 minutes et la
 * session ne s'ouvre qu'après le code (route /api/auth/mfa). Un validateur ou un administrateur qui ne l'a pas encore
 * activée est conduit à « Sécurité du compte » : l'API lui refuse tout le reste tant qu'elle n'est pas active.
 * En cas de refus, retour au formulaire avec le message.
 */
export async function POST(req: NextRequest) {
  const origin = req.headers.get("origin");
  if (!origin || new URL(origin).host !== req.headers.get("host")) {
    return NextResponse.json({ title: "Origine refusée" }, { status: 403 });
  }
  const form = await req.formData();
  const username = String(form.get("username") ?? "").trim();
  const password = String(form.get("password") ?? "");
  const next = safeNext(String(form.get("next") ?? ""));
  const fail = (reason: string) =>
    NextResponse.redirect(
      siteUrl(`/connexion?${new URLSearchParams({ erreur: reason, identifiant: username, next })}`, req),
      303,
    );
  if (!username || !password) return fail("Saisir l'adresse e-mail et le mot de passe.");
  try {
    const session = await passwordLogin(username, password);
    const me = await fetch(`${API_URL}/v1/me`, { headers: { authorization: `Bearer ${session.at}` }, cache: "no-store" });
    if (!me.ok) return fail("Compte inconnu ou désactivé dans RecallPharma.");
    const account = (await me.json()) as { mfa_enabled?: boolean; mfa_required?: boolean };
    if (account.mfa_enabled) {
      const pending: PendingMfa = { session, next, until: Math.floor(Date.now() / 1000) + 300 };
      const res = NextResponse.redirect(siteUrl(`/connexion?${new URLSearchParams({ etape: "code", next })}`, req), 303);
      res.cookies.set(MFA_COOKIE, await seal(pending), cookieOptions(300));
      return res;
    }
    const target = account.mfa_required
      ? `/compte/securite?${new URLSearchParams({ obligatoire: "1", next })}`
      : next;
    const res = NextResponse.redirect(siteUrl(target, req), 303);
    res.cookies.set(SESSION_COOKIE, await seal(session), cookieOptions(8 * 3600));
    return res;
  } catch (e) {
    return fail(e instanceof LoginError ? e.message : "Service de connexion indisponible, réessayer dans un instant.");
  }
}
