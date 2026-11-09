import type { components } from "./api.generated";

export type CurrentUser = components["schemas"]["UserOutput"];
export type Credentials = components["schemas"]["LoginInput"];
type LoginResult = components["schemas"]["LoginOutput"];

export class ApiError extends Error {
  constructor(readonly status: number, readonly retryAfter?: number) {
    super("Request could not be completed");
  }
}

async function request(path: string, init?: RequestInit) {
  const response = await fetch(`/api/v1/auth/${path}`, {
    ...init, cache: "no-store", credentials: "same-origin", redirect: "error",
  });
  if (!response.ok) {
    const seconds = Number(response.headers.get("Retry-After"));
    throw new ApiError(response.status, Number.isFinite(seconds) && seconds > 0
      ? Math.min(Math.ceil(seconds), 3600) : undefined);
  }
  return response;
}

export async function currentUser(signal?: AbortSignal): Promise<CurrentUser | null> {
  try { return await (await request("me", { signal })).json() as CurrentUser; }
  catch (error) { if (error instanceof ApiError && error.status === 401) return null; throw error; }
}

export async function login(credentials: Credentials): Promise<CurrentUser> {
  const response = await request("sessions", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(credentials),
  });
  return ((await response.json()) as LoginResult).user;
}

export async function logout(csrf: string): Promise<void> {
  await request("sessions/current", { method: "DELETE", headers: { "X-CSRF-Token": csrf } });
}

export function loginError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "E-mail ou senha incorretos. Confira os dados e tente novamente.";
    if (error.status === 429) return `Muitas tentativas. Aguarde ${error.retryAfter ?? 60} segundos antes de tentar novamente.`;
    if (error.status === 403) return "O acesso foi recusado. Recarregue a página e tente novamente.";
  }
  return "Não foi possível conectar. Confira sua conexão e tente novamente.";
}
