/** Appels du navigateur vers le BFF Next.js (jamais directement vers l'API). */
export type Problem = { title?: string; detail?: string; status?: number; [key: string]: unknown };

export class BffError extends Error {
  constructor(
    public status: number,
    public problem: Problem,
  ) {
    super(problem.title ?? `Erreur ${status}`);
  }
}

export async function bff<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !(init.body instanceof FormData) && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  const res = await fetch(`/api/bff${path}`, { ...init, headers });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new BffError(res.status, body as Problem);
  return body as T;
}

export function describe(e: unknown): string {
  return e instanceof BffError ? e.message : "Service indisponible, réessayer plus tard.";
}
