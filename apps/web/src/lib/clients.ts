import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";

export type ClientRecord = components["schemas"]["ClientOutput"];
export type ClientCreate = components["schemas"]["ClientCreate"];
export type ContactRecord = components["schemas"]["ContactOutput"];
export type ContactCreate = components["schemas"]["ContactCreate"];
export function createClientApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (id: string) => `/clients/${encodeURIComponent(id)}`;
  async function record<T extends { version: number } = ClientRecord>(response: Response): Promise<T> {
    const value = await response.json() as T;
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
    async contacts(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ContactPage"]> {
      return (await request(`${path(id)}/contacts${pageQuery(cursor)}`, { signal })).json();
    },
    async contact(id: string, contactId: string, signal?: AbortSignal) {
      return record<ContactRecord>(await request(`${path(id)}/contacts/${encodeURIComponent(contactId)}`, { signal }));
    },
    async createContact(id: string, body: ContactCreate, key: string): Promise<components["schemas"]["ContactCreation"]> {
      return (await request(`${path(id)}/contacts`, write("POST", body, undefined, key))).json();
    },
    async updateContact(id: string, contactId: string, body: components["schemas"]["ContactPatch"], version: number) {
      return record<ContactRecord>(await request(`${path(id)}/contacts/${encodeURIComponent(contactId)}`, write("PATCH", body, version)));
    },
  };
}
export type ClientApi = ReturnType<typeof createClientApi>;
