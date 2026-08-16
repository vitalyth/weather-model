import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.WEATHER_API_INTERNAL_URL ??
  (process.env.NODE_ENV === "production" ? "http://backend:8000" : "http://127.0.0.1:8000");

async function proxyRequest(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const targetUrl = new URL(path.join("/"), BACKEND_URL.endsWith("/") ? BACKEND_URL : `${BACKEND_URL}/`);
  targetUrl.search = request.nextUrl.search;

  const headers = new Headers(request.headers);
  headers.delete("host");

  let response: Response;
  try {
    response = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: ["GET", "HEAD"].includes(request.method) ? undefined : await request.arrayBuffer(),
      redirect: "manual"
    });
  } catch (error) {
    return NextResponse.json(
      {
        detail: "Backend API is unreachable from the frontend container.",
        backend_url: BACKEND_URL,
        error: error instanceof Error ? error.message : "Unknown proxy error"
      },
      { status: 502 }
    );
  }

  return new NextResponse(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers: response.headers
  });
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
