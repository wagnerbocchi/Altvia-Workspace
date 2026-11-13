import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";

export type Attachment = components["schemas"]["AttachmentOutput"];
export type AttachmentSummary = components["schemas"]["AttachmentSummary"];
export type IncomingFileSet = components["schemas"]["CaseFileSet"];
export type FileScope = { owner: "ticket"; id: string; purpose: "public" | "note" } | { owner: "work_item"; id: string; purpose: "work" };
export type UploadIntent = { kind: "upload"; file: File; digest: string; version: number; key: string };
export type RetryIntent = { kind: "retry"; id: string; version: number; key: string };

export function createAttachmentApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (id: string) => `/attachments/${encodeURIComponent(id)}`;
  const parent = (scope: FileScope) => `/${scope.owner === "ticket" ? "tickets" : "work-items"}/${encodeURIComponent(scope.id)}/attachments`;
  return {
    async list(scope: FileScope, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["AttachmentPage"]> {
      return (await request(`${parent(scope)}${pageQuery(cursor)}&purpose=${scope.purpose}`, { signal })).json();
    },
    async get(id: string, signal?: AbortSignal): Promise<Attachment> {
      const response = await request(path(id), { signal });
      const value: Attachment = await response.json();
      if (response.headers.get("ETag") !== versionHeader(value.version)) throw Error("File version not confirmed");
      return value;
    },
    async upload(scope: FileScope, intent: UploadIntent, signal: AbortSignal): Promise<components["schemas"]["UploadReceipt"]> {
      const init = write("POST", undefined, intent.version, intent.key);
      const response = await request(`${parent(scope)}?${new URLSearchParams({ purpose: scope.purpose, filename: intent.file.name })}`, {
        ...init, signal, headers: { ...init.headers, "Content-Type": "application/octet-stream", "X-File-Bytes": String(intent.file.size), "X-File-SHA256": intent.digest }, body: intent.file,
      });
      const receipt: components["schemas"]["UploadReceipt"] = await response.json();
      if (response.headers.get("ETag") !== versionHeader(receipt.version)) throw Error("Upload receipt not confirmed");
      return receipt;
    },
    async retry(intent: RetryIntent, signal: AbortSignal): Promise<components["schemas"]["RetryReceipt"]> {
      const response = await request(`${path(intent.id)}/scan-retries`, { ...write("POST", {}, intent.version, intent.key), signal });
      const receipt: components["schemas"]["RetryReceipt"] = await response.json();
      if (response.headers.get("ETag") !== versionHeader(receipt.version) || receipt.attachment_id !== intent.id) throw Error("Scan retry receipt not confirmed");
      return receipt;
    },
    async content(id: string, signal: AbortSignal) {
      return (await request(`${path(id)}/content`, { signal })).blob();
    },
  };
}

export function sameAttachments(left: readonly AttachmentSummary[], right: readonly AttachmentSummary[]) {
  return left.length === right.length && left.every((item, index) => item.id === right[index].id && item.filename === right[index].filename && item.media_type === right[index].media_type && item.bytes === right[index].bytes);
}
