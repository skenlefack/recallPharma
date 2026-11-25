import { type NextRequest, NextResponse } from "next/server";

import { LoginError, SESSION_COOKIE, cookieOptions, passwordLogin, safeNext, seal, siteUrl } from "@/lib/oidc";

/**
 * Formulaire de connexion du site (POST, même origine) : identifiant et mot de passe vérifiés par Keycloak côté serveur,
 * puis session scellée dans un cookie HttpOnly. En cas de refus, retour au formulaire avec le message et l'identifiant.
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
    const res = NextResponse.redirect(siteUrl(next, req), 303);
    res.cookies.set(SESSION_COOKIE, await seal(session), cookieOptions(8 * 3600));
    return res;
  } catch (e) {
    return fail(e instanceof LoginError ? e.message : "Service de connexion indisponible, réessayer dans un instant.");
  }
}
