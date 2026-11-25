/**
 * Client OIDC confidentiel du BFF et session chiffrée. La page de connexion est celle du site : le serveur transmet
 * l'identifiant et le mot de passe à Keycloak (flux « mot de passe », canal serveur authentifié par le secret client) ;
 * l'utilisateur ne voit jamais Keycloak, qui reste l'annuaire (comptes, rôles, verrouillage après échecs).
 * Utilisable depuis le middleware (Edge) comme depuis les routes : Web Crypto et fetch seulement.
 * Les jetons ne quittent jamais le serveur en clair : le navigateur ne détient qu'un cookie HttpOnly scellé (AES-GCM).
 */

export const ISSUER = process.env.RECALLPHARMA_OIDC_ISSUER ?? "http://localhost:8280/realms/recallpharma";
export const CLIENT_ID = process.env.RECALLPHARMA_OIDC_CLIENT_ID ?? "recallpharma-web";
// Secret du royaume de développement ; un autre royaume le refusera, il faut alors le fournir.
const CLIENT_SECRET = process.env.RECALLPHARMA_OIDC_CLIENT_SECRET ?? "dev-only-web-secret";

export const SESSION_COOKIE = "rp_session";
/** En-tête interne posé par le middleware pour les composants serveur et le BFF ; toujours écrasé à l'entrée. */
export const TOKEN_HEADER = "x-rp-access-token";

export type Session = { at: string; rt: string; exp: number };

// Adresse de Keycloak vue du serveur (jeton, déconnexion), si elle diffère de celle du navigateur (conteneurs).
const BACKCHANNEL = process.env.RECALLPHARMA_OIDC_BACKCHANNEL_URL ?? ISSUER;

const endpoint = (name: "token" | "logout") => `${BACKCHANNEL}/protocol/openid-connect/${name}`;

export const cookieOptions = (maxAge: number) => ({
  httpOnly: true,
  sameSite: "lax" as const,
  secure: process.env.NODE_ENV === "production" && !ISSUER.startsWith("http://localhost"),
  path: "/",
  maxAge,
});

// --- Scellement ----------------------------------------------------------------------------------

let keyPromise: Promise<CryptoKey> | null = null;

function sessionKey(): Promise<CryptoKey> {
  const secret = process.env.RECALLPHARMA_SESSION_SECRET;
  if (!secret && process.env.NODE_ENV === "production" && !ISSUER.startsWith("http://localhost")) {
    throw new Error("RECALLPHARMA_SESSION_SECRET est obligatoire hors développement");
  }
  keyPromise ??= crypto.subtle
    .digest("SHA-256", new TextEncoder().encode(secret ?? "recallpharma-dev-session-secret"))
    .then((raw) => crypto.subtle.importKey("raw", raw, "AES-GCM", false, ["encrypt", "decrypt"]));
  return keyPromise;
}

const b64url = (bytes: Uint8Array) =>
  btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const fromB64url = (s: string) =>
  Uint8Array.from(atob(s.replace(/-/g, "+").replace(/_/g, "/")), (c) => c.charCodeAt(0));

export async function seal(value: unknown): Promise<string> {
  const iv = crypto.getRandomValues(new Uint8Array(12));
  const data = new TextEncoder().encode(JSON.stringify(value));
  const ct = new Uint8Array(await crypto.subtle.encrypt({ name: "AES-GCM", iv }, await sessionKey(), data));
  const out = new Uint8Array(iv.length + ct.length);
  out.set(iv);
  out.set(ct, iv.length);
  return b64url(out);
}

export async function unseal<T>(sealed: string | undefined): Promise<T | null> {
  if (!sealed) return null;
  try {
    const bytes = fromB64url(sealed);
    const plain = await crypto.subtle.decrypt({ name: "AES-GCM", iv: bytes.slice(0, 12) }, await sessionKey(), bytes.slice(12));
    return JSON.parse(new TextDecoder().decode(plain)) as T;
  } catch {
    return null;
  }
}

// --- Flux ----------------------------------------------------------------------------------------

type TokenResponse = { access_token: string; refresh_token: string; expires_in: number; id_token?: string };

/** Refus de connexion, avec un message destiné à l'utilisateur. */
export class LoginError extends Error {}

async function tokenRequest(params: Record<string, string>): Promise<TokenResponse> {
  const res = await fetch(endpoint("token"), {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: CLIENT_ID, client_secret: CLIENT_SECRET, ...params }),
    cache: "no-store",
  });
  if (!res.ok) {
    const error = (await res.json().catch(() => ({}))) as { error?: string; error_description?: string };
    const detail = error.error_description ?? "";
    if (/disabled|locked/i.test(detail)) {
      throw new LoginError("Compte désactivé ou verrouillé après plusieurs échecs. Réessayer plus tard ou contacter l'administrateur.");
    }
    if (/not fully set up/i.test(detail)) {
      throw new LoginError("Compte à finaliser (mot de passe ou double authentification) : contacter l'administrateur.");
    }
    if (error.error === "invalid_grant") throw new LoginError("Adresse e-mail ou mot de passe incorrect.");
    throw new Error(`Keycloak a refusé la demande de jeton (${res.status})`);
  }
  return (await res.json()) as TokenResponse;
}

function toSession(t: TokenResponse): Session {
  return { at: t.access_token, rt: t.refresh_token, exp: Math.floor(Date.now() / 1000) + t.expires_in };
}

/** Connexion par identifiant et mot de passe, vérifiés par Keycloak côté serveur. */
export async function passwordLogin(username: string, password: string): Promise<Session> {
  return toSession(await tokenRequest({ grant_type: "password", username, password, scope: "openid" }));
}

export async function refresh(session: Session): Promise<Session> {
  return toSession(await tokenRequest({ grant_type: "refresh_token", refresh_token: session.rt }));
}

/** Ferme la session Keycloak côté serveur (pas de page de confirmation, pas de jeton dans l'URL). */
export async function endSession(session: Session): Promise<void> {
  await fetch(endpoint("logout"), {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: CLIENT_ID, client_secret: CLIENT_SECRET, refresh_token: session.rt }),
    cache: "no-store",
  }).catch(() => undefined);
}

/**
 * Adresse absolue d'un chemin du site, vue du navigateur. Derrière un conteneur, l'URL de la requête porte l'adresse
 * d'écoute interne (0.0.0.0:3000) : RECALLPHARMA_PUBLIC_URL donne alors l'adresse publique.
 */
export function siteUrl(path: string, req: { url: string }): URL {
  return new URL(path, process.env.RECALLPHARMA_PUBLIC_URL ?? req.url);
}

/** Chemin interne uniquement : pas de redirection ouverte vers un autre site. */
export function safeNext(next: string | null | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/validation";
}
