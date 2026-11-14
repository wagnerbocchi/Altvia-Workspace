import type { components, operations } from "./api.generated";
import { createAdminTransport, pageQuery } from "./admin-http";

export type UnifiedWorkPage = components["schemas"]["UnifiedWorkPage"];
export type UnifiedWorkFilters = Omit<NonNullable<operations["listing_api_v1_my_work_unified_get"]["parameters"]["query"]>, "limit" | "cursor">;
export function createUnifiedWorkApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request } = createAdminTransport(csrf, onAuthError);
  return {
    async list(cursor: string | null, signal?: AbortSignal, filters: UnifiedWorkFilters = {}): Promise<UnifiedWorkPage> {
      const query = new URLSearchParams(pageQuery(cursor).slice(1));
      for (const [key, value] of Object.entries(filters)) {
        if (value !== null && value !== undefined && value !== "") query.set(key, String(value));
      }
      return (await request(`/my-work/unified?${query}`, { signal })).json();
    },
  };
}
export type UnifiedWorkApi = ReturnType<typeof createUnifiedWorkApi>;
