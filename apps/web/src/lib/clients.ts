import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";

export type ClientRecord = components["schemas"]["ClientOutput"];
export type ClientCreate = components["schemas"]["ClientCreate"];
export function createClientApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (id: string) => `/clients/${encodeURIComponent(id)}`;
  async function record(response: Response): Promise<ClientRecord> {
    const value = await response.json() as ClientRecord;
    if (response.headers.get("ETag") !== versionHeader(value.version)) throw Error("Resource version not confirmed");
    return value;
  }
  return {
    async list(cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ClientPage"]> {
      return (await request(`/clients${pageQuery(cursor)}`, { signal })).json();
    },
    async get(id: string, signal?: AbortSignal) { return record(await request(path(id), { signal })); },
    async create(body: ClientCreate, key: string): Promise<components["schemas"]["ClientCreation"]> {
      return (await request("/clients", write("POST", body, undefined, key))).json();
    },
    async update(id: string, body: components["schemas"]["ClientPatch"], version: number) {
      return record(await request(path(id), write("PATCH", body, version)));
    },
    async activity(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ActivityPage"]> {
      return (await request(`${path(id)}/activity${pageQuery(cursor)}`, { signal })).json();
    },
  };
}
export type ClientApi = ReturnType<typeof createClientApi>;
