import "server-only";

import { cookies } from "next/headers";

import type { components } from "./api-types";

export type Schemas = components["schemas"];
export type ProductSheet = Schemas["ProductSheet"];
export type SearchResult = Schemas["SearchResult"];
export type Alert = Schemas["AlertOut"];
export type Jurisdiction = Schemas["JurisdictionOut"];
export type Substance = Schemas["SubstanceOut"];
export type Proposal = Schemas["ProposalOut"];

/** Adresse de l'API, connue du seul serveur Next.js (BFF) : le navigateur ne l'appelle jamais. */
export const API_URL = process.env.RECALLPHARMA_API_URL ?? "http://127.0.0.1:8000";
export const SESSION_COOKIE = "rp_user";

export class ApiError extends Error {
  constructor(
    public status: number,
    public problem: { title?: string; detail?: string; [key: string]: unknown },
  ) {
    super(problem.title ?? `Erreur ${status}`);
  }
}

export async function currentUser(): Promise<string | null> {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

/** Appel de l'API depuis le serveur, avec l'identité de la session (en-tête posé ici, jamais par le client). */
export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const user = await currentUser();
  const headers = new Headers(init.headers);
  if (user) headers.set("X-RecallPharma-User", user);
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
