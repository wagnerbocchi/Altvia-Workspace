import type { components } from "./api.generated";
import { createAdminTransport, PAGE_SIZE, versionHeader } from "./admin-http";

export type MailCase = components["schemas"]["CaseDetail"];
export type Promotion = components["schemas"]["PromotionCreate"] | components["schemas"]["PromotionAppend"];
export type PromotionReceipt = components["schemas"]["PromotionReceipt"];
export const caseStates: Record<MailCase["state"], string> = { ready: "A revisar", promoted: "Incluida em chamado", collision: "Em conflito", revoked: "Atestacao revogada" };

export function createMailCaseApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (id: string) => `/mail-cases/${encodeURIComponent(id)}`;
  return {
    async list(state: MailCase["state"] | "", cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["CasePage"]> {
      const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
      if (state) query.set("state", state);
      if (cursor) query.set("cursor", cursor);
      return (await request(`/mail-cases?${query}`, { signal })).json();
    },
    async get(id: string, signal?: AbortSignal): Promise<MailCase> {
      const response = await request(path(id), { signal });
      const row = await response.json() as MailCase;
      if (response.headers.get("ETag") !== versionHeader(row.version)) throw Error("Case version not confirmed");
      return row;
    },
    async promote(id: string, body: Promotion, version: number, key: string): Promise<PromotionReceipt> {
      const receipt = await (await request(`${path(id)}/promotion`, write("POST", body, version, key))).json() as PromotionReceipt;
      if (receipt.case_id !== id || (body.action === "append" && receipt.ticket_id !== body.ticket_id)) throw Error("Promotion receipt not confirmed");
      return receipt;
    },
  };
}
export type MailCaseApi = ReturnType<typeof createMailCaseApi>;
