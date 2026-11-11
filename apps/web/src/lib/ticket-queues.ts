import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";

export type QueueRecord = components["schemas"]["QueueOutput"];
export type CategoryRecord = components["schemas"]["CategoryOutput"];
export type QueuePatch = components["schemas"]["QueuePatch"];
export type QueueMember = components["schemas"]["QueueMemberOutput"];
export type QueueMemberRole = components["schemas"]["QueueMemberRole"]["role_name"];
export type QueueCreate = components["schemas"]["QueueCreate"];

export function createQueueApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (id: string) => `/ticket-queues/${encodeURIComponent(id)}`;
  async function record<T extends { version: number }>(response: Response): Promise<T> {
    const value = await response.json() as T;
    if (response.headers.get("ETag") !== versionHeader(value.version)) {
      throw Error("Resource version not confirmed");
    }
    return value;
  }
  return {
    async list(cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["QueuePage"]> {
      return (await request(`/ticket-queues${pageQuery(cursor)}`, { signal })).json();
    },
    async teams(cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["QueueTeamPage"]> {
      return (await request(`/ticket-queue-teams${pageQuery(cursor)}`, { signal })).json();
    },
    async create(body: QueueCreate, key: string): Promise<components["schemas"]["QueueReceipt"]> {
      return (await request("/ticket-queues", write("POST", body, undefined, key))).json();
    },
    async get(id: string, signal?: AbortSignal) {
      return record<QueueRecord>(await request(path(id), { signal }));
    },
    async update(id: string, body: QueuePatch, version: number) {
      return record<QueueRecord>(await request(path(id), write("PATCH", body, version)));
    },
    async categories(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["CategoryPage"]> {
      return (await request(`${path(id)}/categories${pageQuery(cursor)}`, { signal })).json();
    },
    async createCategory(id: string, name: string, key: string): Promise<components["schemas"]["CategoryReceipt"]> {
      return (await request(`${path(id)}/categories`, write("POST", { name }, undefined, key))).json();
    },
    async updateCategory(id: string, category: string, body: QueuePatch, version: number) {
      return record<CategoryRecord>(await request(`${path(id)}/categories/${encodeURIComponent(category)}`, write("PATCH", body, version)));
    },
    async members(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["QueueMemberPage"]> {
      return (await request(`${path(id)}/members${pageQuery(cursor)}`, { signal })).json();
    },
    async addMember(id: string, body: components["schemas"]["QueueMemberAdd"], version: number, key: string): Promise<components["schemas"]["QueueMemberReceipt"]> {
      return (await request(`${path(id)}/members`, write("POST", body, version, key))).json();
    },
    async changeMember(id: string, userId: string, role: QueueMemberRole | null, version: number) {
      const response = await request(`${path(id)}/members/${encodeURIComponent(userId)}`, write(role === null ? "DELETE" : "PATCH", role === null ? undefined : { role_name: role }, version));
      if (!response.headers.get("ETag")) throw Error("Resource version not confirmed");
    },
    async activity(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ActivityPage"]> {
      return (await request(`${path(id)}/activity${pageQuery(cursor)}`, { signal })).json();
    },
  };
}
export type QueueApi = ReturnType<typeof createQueueApi>;
