import { ApiError, apiRequest, isResourceForbidden } from "./http";

export const PAGE_SIZE = 10;
export function pageQuery(cursor: string | null) {
  const query = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (cursor) query.set("cursor", cursor);
  return `?${query}`;
}
export function versionHeader(version: number) {
  if (!Number.isInteger(version) || version < 1 || version > 2147483647) throw Error("Invalid resource version");
  return `"${version}"`;
}
export function createAdminTransport(csrf: string, onAuthError: (error: unknown) => void) {
  return {
    async request(path: string, init?: RequestInit) {
      try { return await apiRequest(path, init); }
      catch (error) {
        if (error instanceof ApiError && [401, 403].includes(error.status) && !isResourceForbidden(error)) onAuthError(error);
        throw error;
      }
    },
    write(method: string, body?: object, version?: number, key?: string): RequestInit {
      return { method, headers: { "X-CSRF-Token": csrf,
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(version === undefined ? {} : { "If-Match": versionHeader(version) }),
        ...(key ? { "Idempotency-Key": key } : {}),
      }, ...(body ? { body: JSON.stringify(body) } : {}) };
    },
  };
}
