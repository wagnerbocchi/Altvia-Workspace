"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite } from "@/components/team-admin/common";
import { WriteRecovery } from "@/components/work-items/recovery";
import type { WorkspaceSession } from "@/components/workspace-session";
import { createAutomationApi, type AssignmentRun } from "@/lib/automation";

const states: Record<AssignmentRun["state"], string> = { pending: "Pendente", processing: "Em processamento",
  succeeded: "Concluida", triage: "Requer revisao", superseded: "Atribuicao superada", cancelled: "Cancelada", dead: "Falha" };
const errors: Record<NonNullable<AssignmentRun["error_code"]>, string> = {
  authorization_lost: "O acesso necessario mudou. Revise as permissoes antes de tentar novamente.",
  project_unavailable: "Confira o projeto padrao do cliente e se ele, o cliente e a equipe estao ativos.",
  assignee_unavailable: "O responsavel precisa estar ativo e autorizado no chamado e no projeto.",
  ticket_state_changed: "O chamado ja nao esta em um estado elegivel.",
  existing_work_needs_review: "Revise as tarefas ja vinculadas no projeto padrao antes de tentar novamente.",
  invalid_event: "A origem desta execucao precisa de revisao administrativa.",
  unsupported_event: "A origem desta execucao nao e suportada.",
  broker_unavailable: "A entrega sera retomada automaticamente enquanto houver tentativas disponiveis.",
  processing_failed: "Nao foi possivel concluir o processamento. Revise antes de tentar novamente.",
  attempts_exhausted: "As tentativas automaticas terminaram. Revise a causa antes de repetir.",
  rule_disabled: "A regra foi desativada para esta atribuicao. Reativar nao recupera execucoes canceladas.",
  source_superseded: "O responsavel do chamado mudou antes da execucao.",
  lease_expired: "O processamento interrompido sera recuperado automaticamente.",
};
type Intent = { id: string; version: number; key: string };

export function AssignmentRuns({ ticketId, session, available }: { ticketId: string; session: WorkspaceSession; available: boolean }) {
  const api = createAutomationApi(session.user.csrf_token, session.onAuthError);
  const paging = usePaging();
  const query = useQuery({ queryKey: ["assignment-runs", ticketId, paging.cursor], queryFn: ({ signal }) => api.runs(ticketId, paging.cursor, signal), enabled: available });
  const [review, setReview] = useState<AssignmentRun | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (review && session.isCurrent()) document.getElementById("assignment-retry-heading")?.focus();
  }, [review, session]);
  const [notice, setNotice] = useState("");
  const receipt = useRef<string | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const write = useTeamWrite(session, async (intent: Intent) => {
    if (!session.isCurrent()) return;
    if (!receipt.current) {
      const result = await api.retry(ticketId, intent.id, intent.version, intent.key);
      if (!session.isCurrent()) return;
      if (result.execution_id !== intent.id) throw Error("Execution receipt not confirmed");
      receipt.current = intent.key; setAcknowledged(true);
    }
    if (receipt.current !== intent.key) throw Error("Original execution intent required");
    if (!session.isCurrent()) return;
    await query.refetch({ throwOnError: true });
  }, () => {
    receipt.current = null; setAcknowledged(false); setReview(null);
    setNotice("Reagendamento registrado. Atualize para acompanhar o processamento.");
    requestAnimationFrame(() => { if (session.isCurrent()) document.getElementById("assignment-runs-heading")?.focus(); });
  });
  const rows = available && !query.isError ? query.data?.items : undefined;
  const disabled = write.locked || query.isFetching || !available;
  return <section className="admin-section" aria-labelledby="assignment-runs-heading"><h2 id="assignment-runs-heading" tabIndex={-1}>Automacoes do chamado</h2>
    <p className="field-help">Acompanhe as atribuicoes processadas por regras. Execucoes antigas ainda pendentes serao canceladas ao serem processadas depois de desativar a regra. Tarefas existentes permanecem independentes.</p>
    <Button variant="outline" disabled={disabled} onClick={() => void query.refetch()}>Atualizar automacoes</Button>
    {query.isPending && <LoadingRows label="Carregando automacoes..." />}{(query.isError || !available) && <ReadError retry={() => void query.refetch()} />}
    {rows && (rows.length ? <ul className="record-list" aria-label="Execucoes de automacao">{rows.map(row => <li className="team-row" key={row.id}><div className="record-text"><strong>{states[row.state]}</strong>{row.error_code && <p>{errors[row.error_code]}</p>}<span className="record-meta">Tentativas: {row.attempts}</span><time className="record-meta" dateTime={row.updated_at}>{new Date(row.updated_at).toLocaleString("pt-BR")}</time>{row.effect && <Link className="text-link" href={`/work-items/${encodeURIComponent(row.effect.work_item_id)}`}>{row.effect.mode === "adopted" ? "Abrir tarefa existente" : "Abrir tarefa gerada"}</Link>}</div>{row.can_retry && <Button variant="outline" disabled={disabled} onClick={event => { trigger.current = event.currentTarget; setNotice(""); setReview(row); }}>Revisar nova tentativa</Button>}</li>)}</ul> : <p>Nenhuma execucao disponivel nesta pagina. Atribuicoes sem regra ativa nao geram execucoes.</p>)}
    <Paging paging={paging} next={query.data?.next_cursor} label="automacoes" disabled={disabled} />
    {review && available && !query.isError && <section className="confirmation" aria-labelledby="assignment-retry-heading"><h3 id="assignment-retry-heading" tabIndex={-1}>Repetir esta execucao?</h3><p>A regra e a atribuicao originais serao mantidas. O acesso, o projeto e o responsavel serao conferidos novamente.</p><div className="action-row"><Button disabled={disabled} onClick={() => write.submit({ id: review.id, version: review.version, key: crypto.randomUUID() })}>Confirmar nova tentativa</Button><Button variant="outline" disabled={write.locked} onClick={() => { setReview(null); requestAnimationFrame(() => { if (session.isCurrent()) trigger.current?.focus(); }); }}>Cancelar revisao</Button></div></section>}
    {acknowledged ? <div className="read-notice"><p role="status">Reagendamento registrado. A confirmacao esta pendente.</p><Button variant="outline" disabled={write.pending} onClick={write.verify}>Confirmar dados da execucao</Button></div> : <WriteRecovery write={write} reload={async () => { await query.refetch({ throwOnError: true }); setReview(null); }} verifyLabel="Verificar nova tentativa" />}
    {notice && available && !query.isError && <p role="status" className="read-notice">{notice}</p>}
  </section>;
}
