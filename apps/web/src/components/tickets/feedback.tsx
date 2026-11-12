"use client";

import { Button } from "@/components/ui/button";
import { type useTeamWrite, writeError } from "@/components/team-admin/common";
import { ApiError, isResourceForbidden } from "@/lib/http";

export function ticketError(error: unknown) {
  if (error instanceof ApiError) {
    if (isResourceForbidden(error)) return "Sua conta nao pode realizar esta alteracao. A operacao continua pendente. Atualize o chamado para revisar seu acesso ou descarte a edicao.";
    if (error.code === "delivery_ineligible") return "O remetente ou a atestacao do solicitante mudou. Recarregue para revisar as opcoes antes de preparar outro envio.";
    if (error.code === "delivery_exists") return "Esta resposta ja tem um envio registrado. Recarregue para consultar seu estado; nao envie outra copia.";
    if (error.code === "delivery_content_ineligible") return "O texto salvo nao pode ser enviado nesta configuracao. Consulte o administrador.";
    if (error.code === "ticket_parent_inactive") return "O cliente, a equipe ou a fila foi arquivado. Atualize o chamado.";
    if (error.code === "ticket_closed") return "Reabra o chamado antes de editar ou atribuir um responsavel.";
    if (error.code === "invalid_ticket_assignee") return "O responsavel perdeu a elegibilidade. Atualize as opcoes.";
    if (error.code === "invalid_ticket_requester") return "O solicitante nao esta ativo neste cliente. Atualize as opcoes.";
    if (error.code === "invalid_ticket_category") return "A categoria nao esta ativa nesta fila. Atualize as opcoes.";
    if (error.code === "invalid_ticket_transition") return "O estado ou a politica da fila mudou. Recarregue para revisar.";
    if (error.code === "ticket_already_assigned") return "Outro responsavel assumiu este chamado. Recarregue para revisar.";
  }
  return writeError(error);
}

type Write = Pick<ReturnType<typeof useTeamWrite>, "error" | "uncertain" | "pending" | "locked" | "reloading" | "reloadFailed" | "verify" | "reconcile">;
export function TicketFeedback({ write, reload, verifyLabel }: { write: Write; reload: () => Promise<void>; verifyLabel?: string }) {
  const denied = isResourceForbidden(write.error) && write.locked;
  return <>
    {write.error && <div className="read-error">
      <p role="alert">{ticketError(write.error)}</p>
      <div className="action-row">
      {(write.uncertain || denied) && verifyLabel
        ? <Button variant="outline" disabled={write.pending || write.reloading} onClick={write.verify}>{verifyLabel}</Button>
        : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(reload)}>Recarregar e descartar edicao</Button>}
      {denied && verifyLabel && <Button variant="outline" disabled={write.reloading || write.pending} onClick={() => void write.reconcile(reload)}>Recarregar e descartar edicao</Button>}
      </div>
    </div>}
    {write.reloadFailed && <p role="alert" className="error-message">Nao foi possivel atualizar. A operacao continua bloqueada.</p>}
  </>;
}
