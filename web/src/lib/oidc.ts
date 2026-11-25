/**
 * Client OIDC confidentiel du BFF (code d'autorisation + PKCE S256) et session chiffrée.
 * Utilisable depuis le middleware (Edge) comme depuis les routes : Web Crypto et fetch seulement.
 * Les jetons ne quittent jamais le serveur en clair : le navigateur ne détient qu'un cookie HttpOnly scellé (AES-GCM).
 */

export const ISSUER = process.env.RECALLPHARMA_OIDC_ISSUER ?? "http://localhost:8280/realms/recallpharma";
export const CLIENT_ID = process.env.RECALLPHARMA_OIDC_CLIENT_ID ?? "recallpharma-web";
// Secret du royaume de développement ; un autre royaume le refusera, il faut alors le fournir.
const CLIENT_SECRET = process.env.RECALLPHARMA_OIDC_CLIENT_SECRET ?? "dev-only-web-secret";

export const SESSION_COOKIE = "rp_session";
export const LOGIN_COOKIE = "rp_oidc";
/** En-tête interne posé par le middleware pour les composants serveur et le BFF ; toujours écrasé à l'entrée. */
export const TOKEN_HEADER = "x-rp-access-token";

export type Session = { at: string; rt: string; exp: number };
export type PendingLogin = { state: string; verifier: string; nonce: string; next: string };

// Adresse de Keycloak vue du serveur (jeton, déconnexion), si elle diffère de celle du navigateur (conteneurs).
const BACKCHANNEL = process.env.RECALLPHARMA_OIDC_BACKCHANNEL_URL ?? ISSUER;

const endpoint = (name: "auth" | "token" | "logout") =>
  `${name === "auth" ? ISSUER : BACKCHANNEL}/protocol/openid-connect/${name}`;

export const cookieOptions = (maxAge: number) => ({
  httpOnly: true,
  sameSite: "lax" as const, // « strict » ferait perdre le cookie au retour de Keycloak (navigation inter-sites)
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

const random = () => b64url(crypto.getRandomValues(new Uint8Array(32)));

export async function startLogin(redirectUri: string, next: string): Promise<{ url: string; pending: PendingLogin }> {
  const pending: PendingLogin = { state: random(), verifier: random(), nonce: random(), next };
  const challenge = b64url(new Uint8Array(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(pending.verifier))));
  const params = new URLSearchParams({
    client_id: CLIENT_ID,
    response_type: "code",
    scope: "openid",
    redirect_uri: redirectUri,
    state: pending.state,
    nonce: pending.nonce,
    code_challenge: challenge,
    code_challenge_method: "S256",
  });
  return { url: `${endpoint("auth")}?${params}`, pending };
}

type TokenResponse = { access_token: string; refresh_token: string; expires_in: number; id_token?: string };

async function tokenRequest(params: Record<string, string>): Promise<TokenResponse> {
  const res = await fetch(endpoint("token"), {
    method: "POST",
    headers: { "content-type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ client_id: CLIENT_ID, client_secret: CLIENT_SECRET, ...params }),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`Keycloak a refusé la demande de jeton (${res.status})`);
  return (await res.json()) as TokenResponse;
}

function toSession(t: TokenResponse): Session {
  return { at: t.access_token, rt: t.refresh_token, exp: Math.floor(Date.now() / 1000) + t.expires_in };
}

function claims(jwt: string): Record<string, unknown> {
  return JSON.parse(new TextDecoder().decode(fromB64url(jwt.split(".")[1] ?? ""))) as Record<string, unknown>;
}

export async function finishLogin(code: string, redirectUri: string, pending: PendingLogin): Promise<Session> {
  const t = await tokenRequest({ grant_type: "authorization_code", code, redirect_uri: redirectUri, code_verifier: pending.verifier });
  // Jetons reçus directement de Keycloak (canal serveur authentifié) : le nonce suffit à lier la réponse à la demande.
  if (!t.id_token || claims(t.id_token).nonce !== pending.nonce) throw new Error("Nonce OIDC invalide");
  return toSession(t);
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
 * d'écoute interne (0.0.0.0:3000) : RECALLPHARMA_PUBLIC_URL donne alors l'adresse publique, déclarée dans le royaume.
 */
export function siteUrl(path: string, req: { url: string }): URL {
  return new URL(path, process.env.RECALLPHARMA_PUBLIC_URL ?? req.url);
}

/** Chemin interne uniquement : pas de redirection ouverte vers un autre site. */
export function safeNext(next: string | null | undefined): string {
  return next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : "/validation";
}
