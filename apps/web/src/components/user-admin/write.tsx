"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import type { WorkspaceSession } from "@/components/workspace-session";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/http";
import { isUncertain, writeError } from "@/components/team-admin/common";

export function passwordError(value: string) {
  return Array.from(value).length < 14 || new TextEncoder().encode(value).length > 1024
    ? "Use pelo menos 14 caracteres e no máximo 1024 bytes na senha." : "";
}

// Secrets never enter a mutation variable, cache entry or React render snapshot.
// Only this private ref retains an immutable intent for explicit uncertain replay.
export function useAccountWrite<T extends object, R>(session: WorkspaceSession,
  perform: (intent: T) => Promise<R>, confirmed: (result: R) => void) {
  const intent = useRef<T | null>(null);
  const [locked, setLocked] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [reloadFailed, setReloadFailed] = useState(false);
  useEffect(() => () => { intent.current = null; }, []);
  const mutation = useMutation({ mutationFn: async () => {
    if (!intent.current || !session.isCurrent()) throw new ApiError(401);
    return perform(intent.current);
  }, onSuccess(result) {
    intent.current = null;
    if (!session.isCurrent()) return;
    setLocked(false); confirmed(result);
  }, onError(error) {
    if (!isUncertain(error)) intent.current = null;
    if (!session.isCurrent()) { intent.current = null; return; }
    if (!isUncertain(error) && !(error instanceof ApiError && error.status === 409)) setLocked(false);
  } });
  return { locked: locked || reloading, pending: mutation.isPending, error: mutation.error,
    uncertain: isUncertain(mutation.error), reloading, reloadFailed,
    submit(value: T) {
      if (!session.isCurrent() || locked || reloading || intent.current) return;
      intent.current = Object.freeze({ ...value }); setLocked(true); setReloadFailed(false);
      mutation.mutate();
    },
    verify() {
      if (session.isCurrent() && intent.current && !mutation.isPending && !reloading
        && isUncertain(mutation.error)) mutation.mutate();
    },
    async reconcile(reload: () => Promise<void>) {
      if (!session.isCurrent() || mutation.isPending || reloading) return;
      setReloading(true); setReloadFailed(false);
      try {
        await reload();
        if (session.isCurrent() && !isUncertain(mutation.error)) {
          intent.current = null; setLocked(false); mutation.reset();
        }
      } catch { if (session.isCurrent()) setReloadFailed(true); }
      finally { if (session.isCurrent()) setReloading(false); }
    },
  };
}

export function AccountWriteFeedback({ write, reload }: {
  write: { error: unknown; uncertain: boolean; locked: boolean; pending: boolean; reloading: boolean;
    reloadFailed: boolean; verify: () => void; reconcile: (reload: () => Promise<void>) => Promise<void> };
  reload: () => Promise<void>;
}) {
  let message = writeError(write.error);
  if (write.error instanceof ApiError) {
    if (write.error.code === "last_active_admin") message = "Mantenha pelo menos um administrador ativo. Conceda administração a outra conta ativa antes de continuar.";
    if (write.error.code === "account_already_exists") message = "Já existe uma conta com este e-mail. Confira as contas cadastradas.";
    if (write.error.code === "version_exhausted") message = "O limite de alterações desta conta foi atingido. Procure o responsável técnico.";
  }
  return <>
    {write.pending && <p role="status">Salvando solicitação...</p>}
    {!!write.error && <div className="error-message"><p role="alert">{message}</p>
      {write.uncertain ? <Button variant="outline" disabled={write.pending || write.reloading} onClick={write.verify}>Verificar resultado</Button>
        : write.locked && <Button variant="outline" disabled={write.reloading} onClick={() => void write.reconcile(reload)}>Recarregar dados</Button>}
    </div>}
    {write.reloadFailed && <p className="error-message" role="alert">Não foi possível atualizar os dados. A solicitação anterior continua bloqueada.</p>}
  </>;
}
