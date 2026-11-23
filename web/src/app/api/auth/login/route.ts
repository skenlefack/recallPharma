import { type NextRequest, NextResponse } from "next/server";

import { LOGIN_COOKIE, cookieOptions, safeNext, seal, startLogin } from "@/lib/oidc";

/** Démarre la connexion Keycloak : état, nonce et vérificateur PKCE gardés dans un cookie scellé de 10 minutes. */
export async function GET(req: NextRequest) {
  const redirectUri = new URL("/api/auth/callback", req.url).toString();
  const { url, pending } = await startLogin(redirectUri, safeNext(req.nextUrl.searchParams.get("next")));
  const res = NextResponse.redirect(url, 303);
  res.cookies.set(LOGIN_COOKIE, await seal(pending), cookieOptions(600));
  return res;
}
