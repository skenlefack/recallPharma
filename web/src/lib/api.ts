import "server-only";

import { headers as requestHeaders } from "next/headers";
import { cache } from "react";

import type { components } from "./api-types";
import { TOKEN_HEADER } from "./oidc";

export type Schemas = components["schemas"];
export type ProductSheet = Schemas["ProductSheet"];
export type SearchResult = Schemas["SearchResult"];
export type Alert = Schemas["AlertOut"];
export type Jurisdiction = Schemas["JurisdictionOut"];
export type Category = Schemas["CategoryOut"];
export type Substance = Schemas["SubstanceOut"];
export type Proposal = Schemas["ProposalOut"];
export type Me = Schemas["MeOut"];

/** Adresse de l'API, connue du seul serveur Next.js (BFF) : le navigateur ne l'appelle jamais. */
export const API_URL = process.env.RECALLPHARMA_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    public problem: { title?: string; detail?: string; [key: string]: unknown },
  ) {
    super(problem.title ?? `Erreur ${status}`);
  }
}

async function accessToken(): Promise<string | null> {
  return (await requestHeaders()).get(TOKEN_HEADER);
}

/** Compte connecté, tel que l'API le reconnaît à partir du jeton Keycloak (une seule requête par rendu). */
export const currentAccount = cache(async (): Promise<Me | null> => {
  if (!(await accessToken())) return null;
  try {
    return await api<Me>("/v1/me");
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return null;
    throw e;
  }
});

export async function currentUser(): Promise<string | null> {
  return (await currentAccount())?.id ?? null;
}

/** Appel de l'API depuis le serveur, avec le jeton de la session (posé ici, jamais par le client). */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await accessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("authorization", `Bearer ${token}`);
  const res = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  if (!res.ok) {
    const problem = await res.json().catch(() => ({ title: res.statusText }));
    throw new ApiError(res.status, problem);
  }
  return (await res.json()) as T;
}

export function query(params: Record<string, string | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v) q.set(k, v);
  const s = q.toString();
  return s ? `?${s}` : "";
}
