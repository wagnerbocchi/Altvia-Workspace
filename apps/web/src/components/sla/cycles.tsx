"use client";

import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging } from "@/components/team-admin/common";
import type { WorkspaceSession } from "@/components/workspace-session";
import { createSlaApi, type Cycle, type Goal } from "@/lib/sla";

const cycleStates: Record<Cycle["state"], string> = { unconfigured: "Sem politica", evaluating: "Em calculo", ready: "Calculado", stale: "Desatualizado", unavailable: "Calculo indisponivel" };
const goalStates: Record<Goal["status"], string> = { evaluating: "Em calculo", running: "Em andamento", paused: "Pausado", approaching: "Proximo do limite", fulfilled: "Cumprido", unfulfilled: "Nao cumprido", breached: "Prazo violado" };
function instant(value: string | null, timezone: string | null) {
  if (!value) return "Ainda nao registrado";
  try { return new Date(value).toLocaleString("pt-BR", { timeZone: timezone ?? "UTC", timeZoneName: "short" }); }
  catch { return new Date(value).toLocaleString("pt-BR", { timeZone: "UTC", timeZoneName: "short" }); }
}
function duration(seconds: number) {
  return `${Math.floor(seconds / 60)} min ${seconds % 60} s`;
}
function GoalFacts({ goal, name, timezone }: { goal: Goal; name: string; timezone: string | null }) {
  const color = goal.status === "fulfilled" ? "done" : goal.status === "breached" ? "breached" : ["paused", "approaching"].includes(goal.status) ? "blocked" : "open";
  return <div className="sla-goal"><h4 className="work-subheading sla-subheading">{name}</h4>
    <p><span className="record-status" data-state={color}>{goalStates[goal.status]}</span>{goal.corrected && <span className="record-meta">Resultado corrigido por evidencia posterior</span>}</p>
    <dl className="account-details work-facts"><div><dt>Meta</dt><dd>{goal.target_minutes} min uteis</dd></div><div><dt>Tempo computado</dt><dd>{duration(goal.elapsed_business_seconds)}</dd></div><div><dt>Saldo de tempo util</dt><dd>{duration(goal.remaining_business_seconds)}</dd></div><div><dt>Limite calculado</dt><dd>{goal.due_at ? instant(goal.due_at, timezone) : goal.status === "paused" ? "Retomado ao sair da pausa" : "Sem projecao disponivel"}</dd></div>
      {goal.fulfilled_at && <div><dt>Atendimento registrado</dt><dd>{instant(goal.fulfilled_at, timezone)}</dd></div>}
      {goal.breached_at && <div><dt>Violacao preservada no historico</dt><dd>{instant(goal.breached_at, timezone)}</dd></div>}</dl>
  </div>;
}
function CycleFacts({ row, current }: { row: Cycle; current?: boolean }) {
  return <article className="sla-cycle" aria-label={`${current ? "Ciclo atual" : "Ciclo anterior"} ${row.number}`}>
    <h3 className="work-subheading sla-subheading">{current ? "Ciclo atual" : "Ciclo anterior"} {row.number}</h3>
    <p><span className="record-status">{cycleStates[row.state]}</span></p>
    {row.state === "unconfigured" ? <p>Nenhuma politica era aplicavel na abertura deste ciclo. Ativar uma politica agora vale apenas para novos chamados ou reaberturas.</p> : <>
      <dl className="account-details work-facts"><div><dt>Politica capturada</dt><dd>{row.policy_name} - revisao {row.policy_version}</dd></div><div><dt>Calendario capturado</dt><dd>{row.calendar_name} - revisao {row.calendar_version}</dd></div><div><dt>Fuso do calendario</dt><dd>{row.timezone}</dd></div><div><dt>Computado ate</dt><dd>{instant(row.computed_through_at, row.timezone)}</dd></div></dl>
      {row.state === "stale" && <p className="read-notice">Estes valores estao desatualizados. Atualize para verificar se o processamento foi retomado.</p>}
      {row.state === "evaluating" && <p className="field-help">O processamento esta pendente. Os valores parciais nao confirmam o resultado atual.</p>}
      {row.state === "unavailable" && <p className="read-notice">Nao foi possivel calcular este ciclo. Os valores anteriores nao confirmam o resultado atual. Atualize; se persistir, solicite revisao administrativa.</p>}
      {row.first_response && <GoalFacts goal={row.first_response} name="Primeira resposta" timezone={row.timezone} />}
      {row.resolution && <GoalFacts goal={row.resolution} name="Resolucao" timezone={row.timezone} />}
    </>}
    <p className="record-meta">Inicio: {instant(row.start_at, row.timezone)}{row.end_at && ` - Resolvido: ${instant(row.end_at, row.timezone)}`}</p>
  </article>;
}
export function TicketSla({ ticketId, session, available }: { ticketId: string; session: WorkspaceSession; available: boolean }) {
  const cache = useQueryClient();
  const paging = usePaging();
  const api = createSlaApi(session.user.csrf_token, session.onAuthError);
  const query = useQuery({ queryKey: ["ticket-sla", ticketId, paging.cursor], queryFn: ({ signal }) => api.cycles(ticketId, paging.cursor, signal), enabled: available, refetchInterval: available ? 30_000 : false });
  const data = query.isError ? undefined : query.data;
  const acceptances = [data?.current, ...(data?.history ?? [])].map(row => row?.first_response?.fulfilled_at).filter(Boolean).join("|");
  useEffect(() => {
    if (!available || !acceptances || !session.isCurrent()) return;
    // A newly observed acceptance also supersedes the conversation's older send state.
    void cache.invalidateQueries({ queryKey: ["ticket-conversation", ticketId] });
    void cache.invalidateQueries({ queryKey: ["ticket-delivery", ticketId] });
  }, [acceptances, available, cache, session, ticketId]);
  if (!available) return null;
  return <section className="admin-section" aria-labelledby="ticket-sla-heading"><h2 id="ticket-sla-heading">SLA do chamado</h2>
    <p className="field-help">A primeira resposta exige aceite pelo servidor de e-mail. Rascunhos, notas internas e entregas incertas nao contam. O horario comum e o registro persistido apos esse aceite; atrasos nesse registro podem afetar o prazo ou o ciclo. Aceite nao confirma entrega ao destinatario.</p>
    <Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar SLA</Button>
    {query.isPending && <LoadingRows label="Carregando SLA..." />}{query.isError && <ReadError retry={() => void query.refetch()} />}
    {data && <><p className="record-meta">Consultado no servidor: {instant(data.observed_at, "UTC")}</p>
      {data.current ? <CycleFacts row={data.current} current /> : <p>Este chamado e anterior ao acompanhamento de SLA. Sua proxima reabertura podera iniciar um ciclo, sem recriar o passado.</p>}
      {data.history.length > 0 && <div aria-label="Ciclos anteriores de SLA">{data.history.map(row => <CycleFacts key={row.number} row={row} />)}</div>}
      <Paging paging={paging} next={data.next_cursor} label="ciclos de SLA" disabled={query.isFetching} /></>}
  </section>;
}
