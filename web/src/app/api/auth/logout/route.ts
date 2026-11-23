import { type NextRequest, NextResponse } from "next/server";

import { SESSION_COOKIE, type Session, endSession, unseal } from "@/lib/oidc";

/** Déconnexion (POST, même origine) : session Keycloak close côté serveur, cookie effacé. */
export async function POST(req: NextRequest) {
  const origin = req.headers.get("origin");
  if (!origin || new URL(origin).host !== req.headers.get("host")) {
    return NextResponse.json({ title: "Origine refusée" }, { status: 403 });
  }
  const session = await unseal<Session>(req.cookies.get(SESSION_COOKIE)?.value);
  if (session) await endSession(session);
  const res = NextResponse.redirect(new URL("/", req.url), 303);
  res.cookies.delete(SESSION_COOKIE);
  return res;
}
