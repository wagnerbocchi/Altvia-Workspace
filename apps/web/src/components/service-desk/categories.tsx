"use client";

import { useState } from "react";
import { useIsMutating, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import type { WorkspaceSession } from "@/components/workspace-session";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite } from "@/components/team-admin/common";
import type { QueueApi } from "@/lib/ticket-queues";
import { MetadataEditor, queueNameSchema, WriteFeedback } from "./metadata-editor";

export function QueueCategories({ id, api, session, writable, refresh }: {
  id: string; api: QueueApi; session: WorkspaceSession; writable: boolean; refresh: () => Promise<void>;
}) {
  const paging = usePaging();
  const mutating = useIsMutating();
  const query = useQuery({ queryKey: ["queue-categories", id, paging.cursor], queryFn: ({ signal }) => api.categories(id, paging.cursor, signal) });
  const [notice, setNotice] = useState("");
  const form = useForm<{ name: string }>({ resolver: zodResolver(queueNameSchema), defaultValues: { name: "" } });
  const reload = async () => { await Promise.all([refresh(), query.refetch({ throwOnError: true })]); };
  const write = useTeamWrite(session, ({ name, key }: { name: string; key: string }) => api.createCategory(id, name, key), () => {
    form.reset(); setNotice("Categoria cadastrada."); paging.reset();
    void reload().catch(() => { /* Reads expose their own recovery controls. */ });
  });
  return <section className="admin-section" aria-labelledby="queue-categories-heading">
    <h2 id="queue-categories-heading">Categorias da fila</h2>
    {writable && <form className="inline-form" noValidate onSubmit={form.handleSubmit(value => {
      setNotice(""); write.submit({ name: value.name, key: crypto.randomUUID() });
    })}>
      <div className="form-grow">
        <label htmlFor="new-category-name">Nome da nova categoria</label>
        <input id="new-category-name" {...form.register("name")} maxLength={300} disabled={write.locked} aria-invalid={!!form.formState.errors.name} aria-describedby="new-category-error" />
        <p id="new-category-error" className="field-error">{form.formState.errors.name?.message}</p>
      </div>
      <Button type="submit" disabled={write.locked}>{write.pending ? "Cadastrando..." : "Cadastrar categoria"}</Button>
    </form>}
    {notice && <p role="status" className="read-notice">{notice}</p>}
    <WriteFeedback creation write={write} reload={reload} />
    <div className="action-row add-member-action"><Button variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar categorias</Button></div>
    {query.isPending && <LoadingRows label="Carregando categorias..." />}
    {query.isError && <ReadError retry={() => void query.refetch()} />}
    {query.data && (query.data.items.length ? <ul className="record-list" aria-label="Categorias da fila">
      {query.data.items.map(row => <li className="admin-section" key={row.id}>
        <h3>{row.name}</h3><p className="field-help">{row.active ? "Categoria ativa" : "Categoria arquivada"}</p>
        <MetadataEditor record={row} kind="categoria" session={session} writable={writable}
          disabled={query.isFetching || query.isError || mutating > 0}
          update={(body, version) => api.updateCategory(id, row.id, body, version)} refresh={reload} />
      </li>)}
    </ul> : <p>Nenhuma categoria cadastrada nesta pagina.</p>)}
    <Paging paging={paging} next={query.data?.next_cursor} label="categorias" disabled={query.isFetching} />
  </section>;
}
