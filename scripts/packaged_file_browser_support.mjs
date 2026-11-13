// Bounded diagnostics and the packaged browser's existing trusted transport.
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";

export const phases = Object.freeze(["unknown", "launch", "context", "cookie", "navigate", "select_file", "upload", "scan_metadata", "refresh_files", "rejected_block", "download", "select_note", "note_fill", "note_save", "note_reload", "select_public", "draft_fill", "draft_review", "draft_save", "send_review", "send_confirm", "incoming_navigate", "incoming_review", "incoming_promote", "incoming_conversation", "complete", "close"]);
export const scanStates = Object.freeze(["unknown", "invalid", "quarantine", "scanning", "ready", "rejected", "failed"]);
export const initialDiagnostic = () => ({ phase: "launch", file_slot: 0, http_status: 0, scan_state: "unknown", page_errors: 0 });
const integer = (value, max) => Number.isInteger(value) && value >= 0 && value <= max ? value : 0;

export function boundedFailure(state, error) {
  // Construct an allowlist projection: no error.message, stack, extra fields or
  // arbitrary server strings can enter even the private diagnostic file.
  return { schema: 1, phase: phases.includes(state.phase) ? state.phase : "unknown",
    file_slot: integer(state.file_slot, 3), http_status: integer(state.http_status, 599),
    scan_state: scanStates.includes(state.scan_state) ? state.scan_state : "invalid",
    page_errors: integer(state.page_errors, 1000),
    error_kind: error?.name === "AssertionError" ? "assertion" : error?.name === "TimeoutError" ? "timeout" : "browser" };
}

export async function emitBrowserFailure(work, state, error) {
  process.exitCode = 1;
  try { await writeFile(resolve(work, "file-browser-diagnostic.private.json"), JSON.stringify(boundedFailure(state, error)) + "\n", { mode: 0o600 }); }
  catch { /* Parent emits a fixed unavailable status; never print a path/error. */ }
  console.error("Packaged file browser proof failed.");
}

export async function browserGet(page, path) {
  // APIRequestContext has separate Node DNS/TLS. Chromium alone owns the
  // mapped hostname, SPKI certificate trust and real browser cookies here.
  return page.evaluate(async path => {
    const response = await fetch(path);
    return { status: response.status, body: response.ok ? await response.json() : null };
  }, path);
}
