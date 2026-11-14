import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";

export type AssignmentRule = components["schemas"]["RuleOutput"];
export type RuleCreate = components["schemas"]["RuleCreate"];
export type RulePatch = components["schemas"]["RulePatch"];
export type AssignmentRun = components["schemas"]["ExecutionOutput"];
export function createAutomationApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const rules = (queue: string) => `/ticket-queues/${encodeURIComponent(queue)}/automation-rules`;
  const runs = (ticket: string) => `/tickets/${encodeURIComponent(ticket)}/automation-executions`;
  return {
    async rules(queue: string, client: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["RulePage"]> {
      return (await request(`${rules(queue)}${pageQuery(cursor)}&client_id=${encodeURIComponent(client)}`, { signal })).json();
    },
    async rule(queue: string, id: string, signal?: AbortSignal): Promise<AssignmentRule> {
      const response = await request(`${rules(queue)}/${encodeURIComponent(id)}`, { signal });
      const row = await response.json() as AssignmentRule;
      if (response.headers.get("ETag") !== versionHeader(row.version)) throw Error("Rule version not confirmed");
      return row;
    },
    async create(queue: string, body: RuleCreate, version: number, key: string): Promise<components["schemas"]["RuleReceipt"]> {
      return (await request(rules(queue), write("POST", body, version, key))).json();
    },
    async patch(queue: string, id: string, body: RulePatch, version: number, queueVersion: number, key: string): Promise<components["schemas"]["RuleReceipt"]> {
      const mutation = write("PATCH", body, version, key);
      return (await request(`${rules(queue)}/${encodeURIComponent(id)}`, { ...mutation,
        headers: { ...mutation.headers, "If-Match-Queue": versionHeader(queueVersion) } })).json();
    },
    async runs(ticket: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ExecutionPage"]> {
      return (await request(`${runs(ticket)}${pageQuery(cursor)}`, { signal })).json();
    },
    async retry(ticket: string, id: string, version: number, key: string): Promise<components["schemas"]["ExecutionReceipt"]> {
      return (await request(`${runs(ticket)}/${encodeURIComponent(id)}/retry`, write("POST", undefined, version, key))).json();
    },
  };
}
