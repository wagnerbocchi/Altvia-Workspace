"use client";

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { ApiError, isResourceForbidden } from "@/lib/http";
import type { WorkspaceSession } from "@/components/workspace-session";
import { Button } from "@/components/ui/button";

export const nameSchema = z.object({ name: z.string().trim().refine(
  value => Array.from(value).length >= 1 && Array.from(value).length <= 150,
  "Use um nome de 1 a 150 caracteres.",
) });

export function usePaging() {
  const [history, setHistory] = useState<(string | null)[]>([null]);
  const [index, setIndex] = useState(0);
  return { cursor: history[index], index,
    previous: () => setIndex(Math.max(0, index - 1)),
    next: (cursor: string) => { setHistory([...history.slice(0, index + 1), cursor]); setIndex(index + 1); },
    reset: () => { setHistory([null]); setIndex(0); },
  };
}

export function Paging({ paging, next, label, disabled = false }: {
  paging: ReturnType<typeof usePaging>; next?: string | null; label: string; disabled?: boolean;
}) {
  const aliases: Record<string, string> = { "cliente do projeto": "clientes", "equipe responsável": "equipes", "área do projeto": "áreas", "gestor inicial": "contas", "tarefa principal": "tarefas", "responsável": "colaboradores", "adicionar envolvido": "colaboradores" };
  const labels: Record<string, [string, string]> = {
    tarefas: ["Tarefas anteriores", "Próximas tarefas"], comentários: ["Comentários anteriores", "Próximos comentários"],
    colaboradores: ["Colaboradores anteriores", "Próximos colaboradores"],
    "mudanças de estado": ["Estados anteriores", "Próximos estados"],
    projetos: ["Projetos anteriores", "Próximos projetos"], áreas: ["Áreas anteriores", "Próximas áreas"],
    clientes: ["Clientes anteriores", "Próximos clientes"], equipes: ["Equipes anteriores", "Próximas equipes"],
    contas: ["Contas anteriores", "Próximas contas"], acessos: ["Acessos anteriores", "Próximos acessos"],
    atividades: ["Atividades anteriores", "Próximas atividades"],
    automacoes: ["Automacoes anteriores", "Proximas automacoes"],
    registros: ["Registros anteriores", "Proximos registros"],
    contatos: ["Contatos anteriores", "Próximos contatos"],
    marcos: ["Marcos anteriores", "Proximos marcos"],
    filas: ["Filas anteriores", "Proximas filas"],
    categorias: ["Categorias anteriores", "Proximas categorias"],
    chamados: ["Chamados anteriores", "Proximos chamados"],
    notas: ["Notas anteriores", "Proximas notas"],
    solicitante: ["Solicitantes anteriores", "Proximos solicitantes"],
    categoria: ["Categorias anteriores", "Proximas categorias"],
    responsavel: ["Responsaveis anteriores", "Proximos responsaveis"],
    "fila do chamado": ["Filas anteriores", "Proximas filas"],
    "cliente do chamado": ["Clientes anteriores", "Proximos clientes"],
    "equipe da fila": ["Equipes anteriores", "Proximas equipes"],
  };
  const [previousLabel, nextLabel] = labels[aliases[label] ?? label] ?? (label.startsWith("arquivos de ") ? ["Arquivos anteriores", "Proximos arquivos"] : ["Participantes anteriores", "Próximos participantes"]);
  return <nav className="paging" aria-label={`Páginas de ${label}`}>
    <Button type="button" variant="outline" disabled={disabled || paging.index === 0} onClick={paging.previous}>
      {previousLabel}
    </Button><span>Página {paging.index + 1}</span>
    <Button type="button" variant="outline" disabled={disabled || !next} onClick={() => next && paging.next(next)}>
      {nextLabel}
    </Button>
  </nav>;
}

export function isUncertain(error: unknown) {
  return !!error && (!(error instanceof ApiError) || error.status >= 500 || error.status === 408);
}

export function writeError(error: unknown) {
  if (isUncertain(error)) return "Não foi possível confirmar a gravação. Confira o resultado antes de enviar outra solicitação.";
  if (error instanceof ApiError) {
    if (error.code === "name_exists") return "Ja existe um cadastro com esse nome nesta equipe ou fila. Escolha outro nome ou restaure o cadastro existente.";
    if (error.code === "inactive_parent") return "A equipe ou fila foi arquivada. Recarregue os dados antes de continuar.";
    if (error.code === "contact_email_exists") return "Este e-mail ja pertence a um contato deste cliente. Recarregue para revisar o cadastro existente.";
    if (error.code === "client_inactive") return "Este cliente foi arquivado. Recarregue os dados antes de alterar contatos ou selecionar um projeto.";
    if (error.code === "invalid_default_project") return "Escolha um projeto ativo deste cliente com equipe ativa. Recarregue as opcoes.";
    if (error.code === "team_inactive") return "Esta equipe foi arquivada. Recarregue os dados.";
    if (error.code === "account_inactive") return "Esta conta foi desativada. Recarregue antes de escolher outra.";
    if (error.status === 409) return "Os dados foram alterados em outra sessão. Recarregue antes de tentar novamente.";
    if ([401, 403].includes(error.status)) return "Seu acesso precisa ser verificado.";
    if (error.status === 404) return "O registro não está disponível. Recarregue os dados.";
    if (error.status === 422 || error.status === 400) return "Confira os dados informados e tente novamente.";
    if (error.status === 429) return "Muitas solicitações. Aguarde antes de tentar novamente.";
  }
  return "Não foi possível concluir a operação. Tente novamente.";
}

// One retained immutable intent owns duplicate suppression and explicit replay.
// All success effects, including navigation, are fenced to the live session.
export function useTeamWrite<T extends object, R>(session: WorkspaceSession,
  perform: (intent: T) => Promise<R>, confirmed: (result: R, intent: T) => void) {
  const intent = useRef<T | null>(null);
  const [snapshot, setSnapshot] = useState<T | null>(null);
  const [reloading, setReloading] = useState(false);
  const [reloadFailed, setReloadFailed] = useState(false);
  const mutation = useMutation({ mutationFn: perform, onSuccess(result, variables) {
    if (!session.isCurrent()) return;
    intent.current = null; setSnapshot(null); confirmed(result, variables);
  }, onError(error) {
    if (!session.isCurrent()) return;
    if (!isUncertain(error) && !isResourceForbidden(error) && !(error instanceof ApiError && error.status === 409)) {
      intent.current = null; setSnapshot(null);
    }
  } });
  return {
    pending: mutation.isPending, locked: snapshot !== null || reloading, error: mutation.error,
    uncertain: isUncertain(mutation.error), current: snapshot, reloading, reloadFailed,
    submit: (value: T) => {
      if (!session.isCurrent() || intent.current !== null) return;
      intent.current = Object.freeze({ ...value }); setSnapshot(intent.current);
      setReloadFailed(false); mutation.mutate(intent.current);
    },
    verify: () => {
      if (session.isCurrent() && intent.current && !mutation.isPending && !reloading && (isUncertain(mutation.error) || isResourceForbidden(mutation.error))) {
        mutation.mutate(intent.current);
      }
    },
    reconcile: async (reload: () => Promise<void>, preserveIntent = false) => {
      if (!session.isCurrent() || mutation.isPending || reloading) return;
      setReloading(true); setReloadFailed(false);
      try {
        await reload();
        if (session.isCurrent() && !preserveIntent) { intent.current = null; setSnapshot(null); mutation.reset(); }
      } catch { if (session.isCurrent()) setReloadFailed(true); }
      finally { if (session.isCurrent()) setReloading(false); }
    },
  };
}

export function LoadingRows({ label }: { label: string }) {
  return <div role="status" aria-label={label} className="loading-rows">
    <p>{label}</p><span aria-hidden="true" /><span aria-hidden="true" /><span aria-hidden="true" />
  </div>;
}

export function ReadError({ retry, children }: { retry: () => void; children?: React.ReactNode }) {
  return <div className="read-error"><p role="alert">{children ?? "Não foi possível carregar os dados. Confira a conexão e tente novamente."}</p>
    <Button type="button" variant="outline" onClick={retry}>Tentar carregar novamente</Button></div>;
}
