import { type NextRequest, NextResponse } from "next/server";

import { LOGIN_COOKIE, type PendingLogin, SESSION_COOKIE, cookieOptions, finishLogin, seal, unseal } from "@/lib/oidc";

/** Retour de Keycloak : contrôle de l'état, échange du code (secret client + vérificateur PKCE), ouverture de session. */
export async function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;
  const pending = await unseal<PendingLogin>(req.cookies.get(LOGIN_COOKIE)?.value);
  const fail = (reason: string) => {
    const res = NextResponse.redirect(new URL(`/connexion?erreur=${encodeURIComponent(reason)}`, req.url), 303);
    res.cookies.delete(LOGIN_COOKIE);
    return res;
  };
  if (!pending || params.get("state") !== pending.state) return fail("La demande de connexion a expiré, recommencer.");
  if (params.get("error")) return fail(params.get("error_description") ?? "Connexion refusée par Keycloak.");
  const code = params.get("code");
  if (!code) return fail("Réponse de Keycloak incomplète.");
  try {
    const session = await finishLogin(code, new URL("/api/auth/callback", req.url).toString(), pending);
    const res = NextResponse.redirect(new URL(pending.next, req.url), 303);
    res.cookies.delete(LOGIN_COOKIE);
    res.cookies.set(SESSION_COOKIE, await seal(session), cookieOptions(8 * 3600));
    return res;
  } catch {
    return fail("Échange du code refusé, recommencer.");
  }
}
