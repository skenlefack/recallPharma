import { type NextRequest, NextResponse } from "next/server";

import { LOGIN_COOKIE, type PendingLogin, SESSION_COOKIE, cookieOptions, finishLogin, seal, unseal, siteUrl } from "@/lib/oidc";

/** Retour de Keycloak : contrôle de l'état, échange du code (secret client + vérificateur PKCE), ouverture de session. */
export async function GET(req: NextRequest) {
  const params = req.nextUrl.searchParams;
  const pending = await unseal<PendingLogin>(req.cookies.get(LOGIN_COOKIE)?.value);
  const fail = (reason: string) => {
    const res = NextResponse.redirect(siteUrl(`/connexion?erreur=${encodeURIComponent(reason)}`, req), 303);
    res.cookies.delete(LOGIN_COOKIE);
    return res;
  };
  if (!pending || params.get("state") !== pending.state) return fail("La demande de connexion a expiré, recommencer.");
  if (params.get("error")) return fail(params.get("error_description") ?? "Connexion refusée par Keycloak.");
  const code = params.get("code");
  if (!code) return fail("Réponse de Keycloak incomplète.");
  try {
    const session = await finishLogin(code, siteUrl("/api/auth/callback", req).toString(), pending);
    const res = NextResponse.redirect(siteUrl(pending.next, req), 303);
    res.cookies.delete(LOGIN_COOKIE);
    res.cookies.set(SESSION_COOKIE, await seal(session), cookieOptions(8 * 3600));
    return res;
  } catch {
    return fail("Échange du code refusé, recommencer.");
  }
}
