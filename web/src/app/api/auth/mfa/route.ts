import { type NextRequest, NextResponse } from "next/server";

import { API_URL } from "@/lib/api";
import { MFA_COOKIE, type PendingMfa, SESSION_COOKIE, cookieOptions, seal, siteUrl, unseal } from "@/lib/oidc";

/**
 * Seconde étape de connexion (POST, même origine) : le code de l'application d'authentification est vérifié par l'API
 * (anti-rejeu, verrouillage après échecs) ; la session ne s'ouvre qu'ensuite.
 */
export async function POST(req: NextRequest) {
  const origin = req.headers.get("origin");
  if (!origin || new URL(origin).host !== req.headers.get("host")) {
    return NextResponse.json({ title: "Origine refusée" }, { status: 403 });
  }
  const pending = await unseal<PendingMfa>(req.cookies.get(MFA_COOKIE)?.value);
  if (!pending || pending.until < Date.now() / 1000) {
    const res = NextResponse.redirect(
      siteUrl(`/connexion?${new URLSearchParams({ erreur: "Délai dépassé : se reconnecter avec le mot de passe." })}`, req),
      303,
    );
    res.cookies.delete(MFA_COOKIE);
    return res;
  }
  const code = String((await req.formData()).get("code") ?? "").replace(/\s/g, "");
  const check = await fetch(`${API_URL}/v1/me/mfa/verify`, {
    method: "POST",
    headers: { authorization: `Bearer ${pending.session.at}`, "content-type": "application/json" },
    body: JSON.stringify({ code }),
    cache: "no-store",
  }).catch(() => null);
  if (!check?.ok) {
    const problem = (await check?.json().catch(() => ({}))) as { title?: string } | undefined;
    const reason = check?.status === 422 ? "Saisir les 6 chiffres du code." : (problem?.title ?? "Vérification indisponible.");
    return NextResponse.redirect(
      siteUrl(`/connexion?${new URLSearchParams({ etape: "code", erreur: reason, next: pending.next })}`, req),
      303,
    );
  }
  const res = NextResponse.redirect(siteUrl(pending.next, req), 303);
  res.cookies.delete(MFA_COOKIE);
  res.cookies.set(SESSION_COOKIE, await seal(pending.session), cookieOptions(8 * 3600));
  return res;
}
