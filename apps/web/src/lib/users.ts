import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";
import { ApiError } from "./http";

export type Account = components["schemas"]["UserAdminOutput"];
export type RolePage = components["schemas"]["TeamRolePage"];
export type Role = components["schemas"]["TeamRoleOutput"];
export type AccountCreate = { email: string; display_name: string; password: string };
export type SecurityChange =
  | { kind: "activation"; active: boolean }
  | { kind: "password"; password: string }
  | { kind: "platform-admin"; enabled: boolean }
  | { kind: "team-roles"; team_id: string; role_name: Role["role_name"]; enabled: boolean };

export function createAccountApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (id: string) => `/users/${encodeURIComponent(id)}`;
  async function accountResponse(response: Response): Promise<Account> {
    const account = await response.json() as Account;
    if (response.headers.get("ETag") !== versionHeader(account.version)) throw Error("Account version not confirmed");
    if (response.headers.get("X-Session-Revoked") === "true") onAuthError(new ApiError(401));
    return account;
  }
  return {
    async get(id: string, signal?: AbortSignal) {
      return accountResponse(await request(path(id), { signal }));
    },
    async roles(id: string, cursor: string | null, signal?: AbortSignal): Promise<{ page: RolePage; version: number }> {
      const response = await request(`${path(id)}/team-roles${pageQuery(cursor)}`, { signal });
      const tag = response.headers.get("ETag");
      if (!tag || !/^"[1-9][0-9]{0,9}"$/.test(tag)) throw Error("Account role version not confirmed");
      const version = Number(tag.slice(1, -1)); versionHeader(version);
      return { page: await response.json() as RolePage, version };
    },
    async create(body: AccountCreate, key: string) {
      return accountResponse(await request("/users", write("POST", body, undefined, key)));
    },
    async change(id: string, change: SecurityChange, version: number, key: string) {
      const { kind, ...body } = change;
      return accountResponse(await request(`${path(id)}/${kind}`, write("POST", body, version, key)));
    },
  };
}
export type AccountApi = ReturnType<typeof createAccountApi>;
