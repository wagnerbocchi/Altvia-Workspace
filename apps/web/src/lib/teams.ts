import type { components } from "./api.generated";
import { ApiError, apiRequest } from "./http";

export type Team = components["schemas"]["TeamOutput"];
export type TeamPage = components["schemas"]["TeamPage"];
export type UserPage = components["schemas"]["UserPage"];
export type MemberPage = components["schemas"]["MemberPage"];
export type Roster = { page: MemberPage; version: number };
export const PAGE_SIZE = 10;

function pageQuery(cursor: string | null) {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (cursor) query.set("cursor", cursor);
  return `?${query}`;
}

function versionHeader(version: number) {
  if (!Number.isInteger(version) || version < 1 || version > 2147483647) throw Error("Invalid resource version");
  return `"${version}"`;
}

export function createTeamApi(csrf: string, onAuthError: (error: unknown) => void) {
  async function request(path: string, init?: RequestInit) {
    try { return await apiRequest(path, init); }
    catch (error) {
      if (error instanceof ApiError && [401, 403].includes(error.status)) onAuthError(error);
      throw error;
    }
  }
  function write(method: string, body?: object, version?: number, key?: string): RequestInit {
    return { method, headers: {
      "X-CSRF-Token": csrf,
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(version === undefined ? {} : { "If-Match": versionHeader(version) }),
      ...(key ? { "Idempotency-Key": key } : {}),
    }, ...(body ? { body: JSON.stringify(body) } : {}) };
  }
  const teamPath = (id: string) => `/teams/${encodeURIComponent(id)}`;
  return {
    async list(cursor: string | null, signal?: AbortSignal): Promise<TeamPage> {
      return (await request(`/teams${pageQuery(cursor)}`, { signal })).json();
    },
    async get(id: string, signal?: AbortSignal): Promise<Team> {
      const response = await request(teamPath(id), { signal });
      const team = await response.json() as Team;
      if (response.headers.get("ETag") !== versionHeader(team.version)) throw Error("Resource version not confirmed");
      return team;
    },
    async users(cursor: string | null, signal?: AbortSignal): Promise<UserPage> {
      return (await request(`/users${pageQuery(cursor)}`, { signal })).json();
    },
    async members(id: string, cursor: string | null, signal?: AbortSignal): Promise<Roster> {
      const response = await request(`${teamPath(id)}/members${pageQuery(cursor)}`, { signal });
      const tag = response.headers.get("ETag");
      if (!tag || !/^"[1-9][0-9]{0,9}"$/.test(tag)) throw Error("Roster version not confirmed");
      const version = Number(tag.slice(1, -1));
      versionHeader(version);
      return { page: await response.json() as MemberPage, version };
    },
    async create(name: string, key: string): Promise<Team> {
      return (await request("/teams", write("POST", { name }, undefined, key))).json();
    },
    async update(id: string, body: components["schemas"]["TeamPatch"], version: number): Promise<void> {
      await request(teamPath(id), write("PATCH", body, version));
    },
    async add(id: string, userId: string, version: number, key: string): Promise<void> {
      await request(`${teamPath(id)}/members`, write("POST", { user_id: userId }, version, key));
    },
    async remove(id: string, userId: string, version: number): Promise<void> {
      await request(`${teamPath(id)}/members/${encodeURIComponent(userId)}`, write("DELETE", undefined, version));
    },
  };
}
export type TeamApi = ReturnType<typeof createTeamApi>;
