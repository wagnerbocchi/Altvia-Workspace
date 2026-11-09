import type { components } from "./api.generated";
import { ApiError, apiRequest } from "./http";
export { ApiError } from "./http";

export type CurrentUser = components["schemas"]["UserOutput"];
export type Credentials = components["schemas"]["LoginInput"];
type LoginResult = components["schemas"]["LoginOutput"];

async function request(path: string, init?: RequestInit) {
  return apiRequest(`/auth/${path}`, init);
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
