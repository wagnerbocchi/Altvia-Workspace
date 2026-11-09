export class ApiError extends Error {
  constructor(readonly status: number, readonly retryAfter?: number, readonly code?: string) {
    super("Request could not be completed");
  }
}

// The only transport origin is the existing edge. Never follow API redirects.
export async function apiRequest(path: string, init?: RequestInit): Promise<Response> {
  const response = await fetch(`/api/v1${path}`, {
    ...init, cache: "no-store", credentials: "same-origin", redirect: "error",
  });
  if (!response.ok) {
    const seconds = Number(response.headers.get("Retry-After"));
    let code: string | undefined;
    try {
      const body: unknown = await response.json();
      if (body && typeof body === "object" && "code" in body && typeof body.code === "string"
        && body.code.length <= 64) code = body.code;
    } catch { /* A proxy error need not be JSON; never expose its body. */ }
    throw new ApiError(response.status, Number.isFinite(seconds) && seconds > 0
      ? Math.min(Math.ceil(seconds), 3600) : undefined, code);
  }
  return response;
}
