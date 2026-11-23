import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, type Session, TOKEN_HEADER, cookieOptions, refresh, seal, unseal } from "@/lib/oidc";

/**
 * À chaque requête : ouvre la session scellée, renouvelle le jeton d'accès s'il expire dans moins de 30 s,
 * et le transmet aux composants serveur et au BFF par un en-tête interne (jamais accepté du navigateur).
 */
export async function middleware(req: NextRequest) {
  const headers = new Headers(req.headers);
  headers.delete(TOKEN_HEADER);
  const raw = req.cookies.get(SESSION_COOKIE)?.value;
  if (!raw) return NextResponse.next({ request: { headers } });

  let session = await unseal<Session>(raw);
  let renewed = false;
  if (session && session.exp - 30 < Date.now() / 1000) {
    session = await refresh(session).catch(() => null);
    renewed = true;
  }
  if (session) headers.set(TOKEN_HEADER, session.at);
  const res = NextResponse.next({ request: { headers } });
  if (!session) res.cookies.delete(SESSION_COOKIE);
  else if (renewed) res.cookies.set(SESSION_COOKIE, await seal(session), cookieOptions(8 * 3600));
  return res;
}

export const config = { matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"] };
