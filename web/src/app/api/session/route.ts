import { type NextRequest, NextResponse } from "next/server";

import { DEMO_ACCOUNTS } from "@/lib/accounts";
import { SESSION_COOKIE } from "@/lib/api";

/** Connexion de démonstration : choisit un compte fictif. À remplacer par le flux OIDC de Keycloak. */
export async function POST(req: NextRequest) {
  const form = await req.formData();
  const id = String(form.get("account") ?? "");
  const res = NextResponse.redirect(new URL(String(form.get("next") || "/validation"), req.url), 303);
  if (!DEMO_ACCOUNTS.some((a) => a.id === id)) {
    res.cookies.delete(SESSION_COOKIE);
    return res;
  }
  res.cookies.set(SESSION_COOKIE, id, {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: 8 * 3600,
  });
  return res;
}
