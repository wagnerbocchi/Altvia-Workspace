import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";
export { PAGE_SIZE } from "./admin-http";

export type Team = components["schemas"]["TeamOutput"];
export type TeamPage = components["schemas"]["TeamPage"];
export type UserPage = components["schemas"]["UserPage"];
export type MemberPage = components["schemas"]["MemberPage"];
export type Roster = { page: MemberPage; version: number };
export function createTeamApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
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
