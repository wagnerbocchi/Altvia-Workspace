import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";

export type Calendar = components["schemas"]["CalendarOutput"];
export type CalendarSummary = components["schemas"]["CalendarSummary"];
export type CalendarCreate = components["schemas"]["CalendarCreate"];
export type CalendarPatch = components["schemas"]["CalendarPatch"];
export type Policy = components["schemas"]["PolicyOutput"];
export type PolicyCreate = components["schemas"]["PolicyCreate"];
export type PolicyPatch = components["schemas"]["PolicyPatch"];
export type Cycle = components["schemas"]["SlaCycleOutput"];
export type Goal = components["schemas"]["SlaGoalOutput"];
export type PolicyCalendar = components["schemas"]["PolicyCalendarSnapshot"];

export function createSlaApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (queue: string, kind: "business-calendars" | "sla-policies") => `/ticket-queues/${encodeURIComponent(queue)}/${kind}`;
  async function record<T extends { version: number }>(response: Response): Promise<T> {
    const row = await response.json() as T;
    if (response.headers.get("ETag") !== versionHeader(row.version)) throw Error("SLA version not confirmed");
    return row;
  }
  const patch = (body: CalendarPatch | PolicyPatch, version: number, queueVersion: number, key: string) => {
    const mutation = write("PATCH", body, version, key);
    return { ...mutation, headers: { ...mutation.headers, "If-Match-Queue": versionHeader(queueVersion) } };
  };
  return {
    async calendars(queue: string, client: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["CalendarPage"]> {
      return (await request(`${path(queue, "business-calendars")}${pageQuery(cursor)}&client_id=${encodeURIComponent(client)}`, { signal })).json();
    },
    async calendar(queue: string, id: string, signal?: AbortSignal) {
      return record<Calendar>(await request(`${path(queue, "business-calendars")}/${encodeURIComponent(id)}`, { signal }));
    },
    async createCalendar(queue: string, body: CalendarCreate, version: number, key: string): Promise<components["schemas"]["CalendarReceipt"]> {
      return (await request(path(queue, "business-calendars"), write("POST", body, version, key))).json();
    },
    async patchCalendar(queue: string, id: string, body: CalendarPatch, version: number, queueVersion: number, key: string): Promise<components["schemas"]["CalendarReceipt"]> {
      return (await request(`${path(queue, "business-calendars")}/${encodeURIComponent(id)}`, patch(body, version, queueVersion, key))).json();
    },
    async policies(queue: string, client: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["PolicyPage"]> {
      return (await request(`${path(queue, "sla-policies")}${pageQuery(cursor)}&client_id=${encodeURIComponent(client)}`, { signal })).json();
    },
    async policy(queue: string, id: string, signal?: AbortSignal) {
      return record<Policy>(await request(`${path(queue, "sla-policies")}/${encodeURIComponent(id)}`, { signal }));
    },
    async policyCalendar(queue: string, id: string, signal?: AbortSignal): Promise<PolicyCalendar> {
      return (await request(`${path(queue, "sla-policies")}/${encodeURIComponent(id)}/calendar-snapshot`, { signal })).json();
    },
    async createPolicy(queue: string, body: PolicyCreate, version: number, key: string): Promise<components["schemas"]["PolicyReceipt"]> {
      return (await request(path(queue, "sla-policies"), write("POST", body, version, key))).json();
    },
    async patchPolicy(queue: string, id: string, body: PolicyPatch, version: number, queueVersion: number, key: string): Promise<components["schemas"]["PolicyReceipt"]> {
      return (await request(`${path(queue, "sla-policies")}/${encodeURIComponent(id)}`, patch(body, version, queueVersion, key))).json();
    },
    async cycles(ticket: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["SlaCyclePage"]> {
      return (await request(`/tickets/${encodeURIComponent(ticket)}/sla${pageQuery(cursor)}`, { signal })).json();
    },
  };
}
