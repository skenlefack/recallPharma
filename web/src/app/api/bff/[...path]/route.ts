import { type NextRequest, NextResponse } from "next/server";

import { API_URL } from "@/lib/api";
import { TOKEN_HEADER } from "@/lib/oidc";

/**
 * BFF : les écritures du navigateur passent ici. Le jeton vient de la session scellée (via le middleware), jamais du client,
 * et une requête d'une autre origine est refusée (protection CSRF, en plus de SameSite=Strict).
 */
async function proxy(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  if (!path.length || (path[0] !== "v1" && path[0] !== "health")) {
    return NextResponse.json({ title: "Chemin non autorisé" }, { status: 404 });
  }
  if (req.method !== "GET") {
    const origin = req.headers.get("origin");
    if (!origin || new URL(origin).host !== req.headers.get("host")) {
      return NextResponse.json({ title: "Origine refusée" }, { status: 403 });
    }
  }
  const headers = new Headers();
  const contentType = req.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const token = req.headers.get(TOKEN_HEADER);
  if (token) headers.set("authorization", `Bearer ${token}`);

  const target = `${API_URL}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const res = await fetch(target, {
    method: req.method,
    headers,
    body: req.method === "GET" ? undefined : await req.arrayBuffer(),
    cache: "no-store",
  });
  const type = res.headers.get("content-type") ?? "application/json";
  if (type.startsWith("text/event-stream")) {
    // Flux du Copilot : relayé au fil de l'eau, sans mise en mémoire tampon.
    return new NextResponse(res.body, {
      status: res.status,
      headers: { "content-type": type, "cache-control": "no-cache, no-transform", "x-accel-buffering": "no" },
    });
  }
  return new NextResponse(res.status === 204 ? null : await res.arrayBuffer(), {
    status: res.status,
    headers: { "content-type": type },
  });
}

export { proxy as DELETE, proxy as GET, proxy as POST, proxy as PUT };
