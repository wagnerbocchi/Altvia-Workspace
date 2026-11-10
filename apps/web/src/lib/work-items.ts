import type { components } from "./api.generated";
import { createAdminTransport, pageQuery, versionHeader } from "./admin-http";

export type WorkRecord = components["schemas"]["WorkOutput"];
export type WorkCreate = components["schemas"]["WorkCreate"];
export type WorkPatch = components["schemas"]["WorkPatch"];
export type WorkTransition = components["schemas"]["Transition"];
export type WorkDue = WorkCreate["due"];
export function createWorkApi(csrf: string, onAuthError: (error: unknown) => void) {
  const { request, write } = createAdminTransport(csrf, onAuthError);
  const path = (id: string) => `/work-items/${encodeURIComponent(id)}`;
  async function record(response: Response): Promise<WorkRecord> {
    const result = await response.json() as WorkRecord;
    if (response.headers.get("ETag") !== versionHeader(result.version)) throw Error("Resource version not confirmed");
    return result;
  }
  return {
    async list(project: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["WorkPage"]> {
      return (await request(`/work-items${pageQuery(cursor)}&project_id=${encodeURIComponent(project)}`, { signal })).json();
    },
    async get(id: string, signal?: AbortSignal) { return record(await request(path(id), { signal })); },
    async create(body: WorkCreate, key: string): Promise<components["schemas"]["WorkReceipt"]> {
      return (await request("/work-items", write("POST", body, undefined, key))).json();
    },
    async update(id: string, body: WorkPatch, version: number) { return record(await request(path(id), write("PATCH", body, version))); },
    async transition(id: string, body: WorkTransition, version: number, key: string) {
      return record(await request(`${path(id)}/transitions`, write("POST", body, version, key)));
    },
    async candidates(project: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["CandidatePage"]> {
      return (await request(`/projects/${encodeURIComponent(project)}/work-candidates${pageQuery(cursor)}`, { signal })).json();
    },
    async comments(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["CommentPage"]> {
      return (await request(`${path(id)}/comments${pageQuery(cursor)}`, { signal })).json();
    },
    async comment(id: string, body: string, version: number, key: string): Promise<components["schemas"]["CommentOutput"]> {
      return (await request(`${path(id)}/comments`, write("POST", { body }, version, key))).json();
    },
    async activity(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["ActivityPage"]> {
      return (await request(`${path(id)}/activity${pageQuery(cursor)}`, { signal })).json();
    },
    async states(id: string, cursor: string | null, signal?: AbortSignal): Promise<components["schemas"]["StatePage"]> {
      return (await request(`${path(id)}/status-history${pageQuery(cursor)}`, { signal })).json();
    },
  };
}
export type WorkApi = ReturnType<typeof createWorkApi>;
export const workStatuses: Record<string, string> = { todo: "A fazer", in_progress: "Em andamento", blocked: "Bloqueada", done: "Concluída", cancelled: "Cancelada" };
export const workPriorities: Record<string, string> = { low: "Baixa", medium: "Média", high: "Alta", critical: "Crítica" };
export function dueLabel(row: WorkRecord) {
  if (!row.due) return "Sem prazo";
  if (row.due.precision === "date") {
    const [year, month, day] = row.due.date.split("-");
    return `${day}/${month}/${year} (${row.due.timezone})`;
  }
  return new Date(row.due.instant).toLocaleString("pt-BR");
}
