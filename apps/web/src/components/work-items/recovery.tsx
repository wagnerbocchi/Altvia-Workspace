"use client";

import { Button } from "@/components/ui/button";
import { type useTeamWrite, writeError } from "@/components/team-admin/common";
import { ApiError } from "@/lib/http";

type Recovery = Pick<ReturnType<typeof useTeamWrite>, "error" | "pending" | "locked" | "uncertain" | "verify" | "reconcile" | "reloading" | "reloadFailed">;
function errorText(error: unknown) {
  if (error instanceof ApiError) {
    if (error.code === "project_inactive") return "O projeto, seu cliente ou sua equipe foi arquivado. Novas alterações estão bloqueadas.";
    if (error.code === "parent_cycle") return "Esta tarefa principal criaria um ciclo. Recarregue e escolha outra tarefa.";
    if (error.code === "invalid_transition") return "Confira o estado, o motivo e a confirmação de encerramento. Recarregue antes de tentar novamente.";
    if (error.code === "invalid_contributor") return "Um responsável ou envolvido já não está disponível neste projeto. Atualize as opções.";
    if (error.code === "invalid_due") return "Confira a data e o fuso do prazo. Essa combinação não é válida.";
  }
  return writeError(error);
}
export function WriteRecovery({ write, reload, verifyLabel }: { write: Recovery; reload: () => Promise<void>; verifyLabel?: string }) {
  return <>{write.error && <div className="read-error"><p role="alert">{errorText(write.error)}</p>
    {write.uncertain && verifyLabel ? <Button variant="outline" disabled={write.pending} onClick={write.verify}>{verifyLabel}</Button>
      : (write.locked || (write.error instanceof ApiError && write.error.code === "invalid_contributor")) && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(reload)}>Recarregar e descartar edição</Button>}
  </div>}{write.reloadFailed && <p role="alert" className="error-message">Não foi possível atualizar. A operação continua bloqueada.</p>}</>;
}
