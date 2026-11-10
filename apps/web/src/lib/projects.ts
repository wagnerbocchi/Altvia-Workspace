import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";

export type ProjectRecord = components["schemas"]["ProjectOutput"];
export type ProjectCreate = components["schemas"]["ProjectCreate"];
export type ProjectPatch = components["schemas"]["ProjectPatch"];
export type ProjectMember = components["schemas"]["ProjectMemberOutput"];
export type ProjectMemberRole = components["schemas"]["ProjectMemberRole"]["role_name"];
export type AreaRecord = components["schemas"]["AreaOutput"];
export function createProjectApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (id: string) => `/projects/${encodeURIComponent(id)}`;
  async function record<T extends { version: number }>(response: Response): Promise<T> {
    const value = await response.json() as T;
    if (response.headers.get("ETag") !== versionHeader(value.version)) throw Error("Resource version not confirmed");
    return value;
  }
  return {
    async list(cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ProjectPage"]> {
      return (await request(`/projects${pageQuery(cursor)}`, { signal })).json();
    },
    async forClient(clientId: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ProjectPage"]> {
      return (await request(`/projects${pageQuery(cursor)}&client_id=${encodeURIComponent(clientId)}`, { signal })).json();
    },
    async get(id: string, signal?: AbortSignal) { return record<ProjectRecord>(await request(path(id), { signal })); },
    async create(body: ProjectCreate, key: string): Promise<components["schemas"]["ProjectCreation"]> {
      return (await request("/projects", write("POST", body, undefined, key))).json();
    },
    async update(id: string, body: ProjectPatch, version: number) {
      return record<ProjectRecord>(await request(path(id), write("PATCH", body, version)));
    },
    async members(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ProjectMemberPage"]> {
      return (await request(`${path(id)}/members${pageQuery(cursor)}`, { signal })).json();
    },
    async addMember(id: string, body: components["schemas"]["ProjectMemberAdd"], version: number, key: string): Promise<components["schemas"]["ProjectMemberReceipt"]> {
      return (await request(`${path(id)}/members`, write("POST", body, version, key))).json();
    },
    async changeMember(id: string, userId: string, role: ProjectMemberRole | null, version: number) {
      const response = await request(`${path(id)}/members/${encodeURIComponent(userId)}`,
        write(role === null ? "DELETE" : "PATCH", role === null ? undefined : { role_name: role }, version));
      const current = Number(response.headers.get("ETag")?.replaceAll('"', ""));
      if (response.headers.get("ETag") !== versionHeader(current)) throw Error("Resource version not confirmed");
    },
    async activity(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ActivityPage"]> {
      return (await request(`${path(id)}/activity${pageQuery(cursor)}`, { signal })).json();
    },
    async areas(cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["AreaPage"]> {
      return (await request(`/operational-areas${pageQuery(cursor)}`, { signal })).json();
    },
    async createArea(name: string, key: string): Promise<AreaRecord> {
      return (await request("/operational-areas", write("POST", { name }, undefined, key))).json();
    },
    async updateArea(id: string, body: components["schemas"]["AreaPatch"], version: number) {
      return record<AreaRecord>(await request(`/operational-areas/${encodeURIComponent(id)}`, write("PATCH", body, version)));
    },
  };
}
export type ProjectApi = ReturnType<typeof createProjectApi>;
