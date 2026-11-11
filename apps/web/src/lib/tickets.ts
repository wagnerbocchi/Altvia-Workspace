import type { components } from "./api.generated";
import { createAdminTransport, PAGE_SIZE, pageQuery, versionHeader } from "./admin-http";

export type TicketRecord = components["schemas"]["TicketOutput"];
export type TicketCreate = components["schemas"]["TicketCreate"];
export type TicketPatch = components["schemas"]["TicketPatch"];
export type TicketTransition = components["schemas"]["TicketTransition"];
export type TicketFilters = Partial<Pick<TicketRecord, "queue_id" | "client_id" | "status" | "priority" | "assignee_id">> & { q?: string; unassigned?: boolean };
export const ticketStatuses: Record<TicketRecord["status"], string> = {
  new: "Novo", open: "Aberto", pending_customer: "Aguardando cliente",
  pending_third_party: "Aguardando terceiro", resolved: "Resolvido", closed: "Fechado",
};
export const ticketPriorities: Record<TicketRecord["priority"], string> = {
  low: "Baixa", medium: "Media", high: "Alta", critical: "Critica",
};

export function createTicketApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (id: string) => `/tickets/${encodeURIComponent(id)}`;
  const choices = (queue: string, client?: string) => `/ticket-choices/${encodeURIComponent(queue)}/clients${client ? `/${encodeURIComponent(client)}` : ""}`;
  async function record(response: Response): Promise<TicketRecord> {
    const value = await response.json() as TicketRecord;
    if (response.headers.get("ETag") !== versionHeader(value.version)) throw Error("Resource version not confirmed");
    return value;
  }
  return {
    async list(filters: TicketFilters, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["TicketPage"]> {
      const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
      for (const [key, value] of Object.entries(filters)) {
        if (value !== undefined && value !== "" && value !== false) query.set(key, String(value));
      }
      if (cursor) query.set("cursor", cursor);
      return (await request(`/tickets?${query}`, { signal })).json();
    },
    async get(id: string, signal?: AbortSignal) { return record(await request(path(id), { signal })); },
    async create(body: TicketCreate, key: string): Promise<components["schemas"]["TicketReceipt"]> {
      return (await request("/tickets", write("POST", body, undefined, key))).json();
    },
    async update(id: string, body: TicketPatch, version: number) { return record(await request(path(id), write("PATCH", body, version))); },
    async claim(id: string, version: number, key: string): Promise<components["schemas"]["TicketReceipt"]> {
      return (await request(`${path(id)}/claim`, write("POST", {}, version, key))).json();
    },
    async transition(id: string, body: TicketTransition, version: number, key: string): Promise<components["schemas"]["TicketTransitionReceipt"]> {
      return (await request(`${path(id)}/transitions`, write("POST", body, version, key))).json();
    },
    async queues(cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["TicketQueueChoices"]> {
      return (await request(`/ticket-choices/queues${pageQuery(cursor)}`, { signal })).json();
    },
    async clients(queue: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["TicketClientChoices"]> {
      return (await request(`${choices(queue)}${pageQuery(cursor)}`, { signal })).json();
    },
    async requesters(queue: string, client: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["RequesterPage"]> {
      return (await request(`${choices(queue, client)}/requesters${pageQuery(cursor)}`, { signal })).json();
    },
    async assignees(queue: string, client: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["CandidatePage"]> {
      return (await request(`${choices(queue, client)}/assignees${pageQuery(cursor)}`, { signal })).json();
    },
    async states(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["TicketStates"]> {
      return (await request(`${path(id)}/status-history${pageQuery(cursor)}`, { signal })).json();
    },
    async activity(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ActivityPage"]> {
      return (await request(`${path(id)}/activity${pageQuery(cursor)}`, { signal })).json();
    },
  };
}
export type TicketApi = ReturnType<typeof createTicketApi>;
