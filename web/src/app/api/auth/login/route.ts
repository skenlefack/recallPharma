import { type NextRequest, NextResponse } from "next/server";

import { LOGIN_COOKIE, cookieOptions, safeNext, seal, startLogin, siteUrl } from "@/lib/oidc";

/** Démarre la connexion Keycloak : état, nonce et vérificateur PKCE gardés dans un cookie scellé de 10 minutes. */
export async function GET(req: NextRequest) {
  const redirectUri = siteUrl("/api/auth/callback", req).toString();
  const { url, pending } = await startLogin(redirectUri, safeNext(req.nextUrl.searchParams.get("next")));
  const res = NextResponse.redirect(url, 303);
  res.cookies.set(LOGIN_COOKIE, await seal(pending), cookieOptions(600));
  return res;
}
