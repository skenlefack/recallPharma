import { type NextRequest, NextResponse } from "next/server";

import { API_URL, SESSION_COOKIE } from "@/lib/api";

/**
 * BFF : les écritures du navigateur passent ici. L'identité vient du cookie HttpOnly, jamais du client,
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
  const user = req.cookies.get(SESSION_COOKIE)?.value;
  if (user) headers.set("X-RecallPharma-User", user);

  const target = `${API_URL}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const res = await fetch(target, {
    method: req.method,
    headers,
    body: req.method === "GET" ? undefined : await req.arrayBuffer(),
    cache: "no-store",
  });
  return new NextResponse(await res.arrayBuffer(), {
    status: res.status,
    headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
  });
}

export { proxy as GET, proxy as POST, proxy as PUT };
