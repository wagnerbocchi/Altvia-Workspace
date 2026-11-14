import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";

export type TicketWorkPage = components["schemas"]["TicketWorkPage"];
export type WorkTicketPage = components["schemas"]["WorkTicketPage"];
export type TicketWorkChoices = components["schemas"]["TicketWorkChoices"];
export type TicketWorkReceipt = components["schemas"]["TicketWorkReceipt"];
export type LinkFilters = { project_id?: string; q?: string };
export type LinkIntent = Readonly<{
  operation: "link" | "unlink";
  ticketId: string;
  workItemId: string;
  ticketVersion: number;
  workItemVersion: number;
  key: string;
}>;

export function createTicketWorkApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (id: string) => `/tickets/${encodeURIComponent(id)}`;
  function mutation(intent: LinkIntent): RequestInit {
    const init = write(intent.operation === "link" ? "POST" : "DELETE",
      intent.operation === "link" ? { work_item_id: intent.workItemId } : undefined,
      intent.ticketVersion, intent.key);
    return { ...init, headers: { ...init.headers, "If-Match-Work-Item": versionHeader(intent.workItemVersion) } };
  }
  return {
    async work(ticketId: string, cursor: string | null, signal?: AbortSignal): Promise<TicketWorkPage> {
      return (await request(`${path(ticketId)}/work-items${pageQuery(cursor)}`, { signal })).json();
    },
    async tickets(workItemId: string, cursor: string | null, signal?: AbortSignal): Promise<WorkTicketPage> {
      return (await request(`/work-items/${encodeURIComponent(workItemId)}/tickets${pageQuery(cursor)}`, { signal })).json();
    },
    async choices(ticketId: string, cursor: string | null, filters: LinkFilters, signal?: AbortSignal): Promise<TicketWorkChoices> {
      const query = new URLSearchParams(pageQuery(cursor).slice(1));
      for (const [key, value] of Object.entries(filters)) if (value) query.set(key, value);
      return (await request(`${path(ticketId)}/work-item-choices?${query}`, { signal })).json();
    },
    async link(intent: LinkIntent): Promise<TicketWorkReceipt> {
      return (await request(`${path(intent.ticketId)}/work-items`, mutation(intent))).json();
    },
    async unlink(intent: LinkIntent): Promise<void> {
      const response = await request(`${path(intent.ticketId)}/work-items/${encodeURIComponent(intent.workItemId)}`, mutation(intent));
      if (response.status !== 204) throw Error("Unlink receipt not confirmed");
    },
  };
}
