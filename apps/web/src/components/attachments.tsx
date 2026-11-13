"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Paperclip } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingRows, Paging, ReadError, usePaging, useTeamWrite, writeError } from "@/components/team-admin/common";
import { useWorkspaceSession } from "@/components/workspace-session";
import { createAttachmentApi, type Attachment, type AttachmentSummary, type FileScope, type IncomingFileSet, type RetryIntent, type UploadIntent } from "@/lib/attachments";
import { ApiError, isResourceForbidden } from "@/lib/http";

const stateLabels: Record<Attachment["state"], string> = { quarantine: "Em quarentena - aguardando verificacao", scanning: "Verificando seguranca", ready: "Pronto para uso", rejected: "Rejeitado - uso bloqueado", failed: "Verificacao falhou" };
const scopeLabels = { public: "resposta publica", note: "nota interna", work: "comentario interno" };
export function AttachmentReview({ files = [] }: { files: readonly AttachmentSummary[] | undefined }) {
  return <div className="attachment-review"><strong>Anexos ({files.length})</strong>{files.length ? <ul className="attachment-names">{files.map(file => <li key={file.id}>{file.filename} <span className="record-meta">({file.bytes.toLocaleString("pt-BR")} bytes)</span></li>)}</ul> : <p className="field-help">Nenhum arquivo incluido.</p>}</div>;
}

function FileDownload({ file, disabled = false }: { file: AttachmentSummary; disabled?: boolean }) {
  const session = useWorkspaceSession();
  const api = createAttachmentApi(session.user.csrf_token, session.onAuthError);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const urls = useRef(new Set<string>());
  useEffect(() => () => { controller.current?.abort(); for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear(); }, []);
  const download = async () => {
    if (disabled || busy || !session.isCurrent()) return;
    setBusy(true); setError("");
    const abort = new AbortController(); controller.current = abort;
    try {
      // Immutable link summaries never stand in for current download authority.
      const current = await api.get(file.id, abort.signal);
      if (!session.isCurrent() || abort.signal.aborted) return;
      if (!current.can_download) { setError("Este arquivo ainda nao pode ser baixado. Atualize os arquivos."); return; }
      const blob = await api.content(file.id, abort.signal);
      if (!session.isCurrent() || abort.signal.aborted) return;
      const url = URL.createObjectURL(blob); urls.current.add(url);
      const anchor = document.createElement("a"); anchor.href = url; anchor.download = current.filename;
      anchor.click();
      setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url); }, 0);
    } catch { if (session.isCurrent() && !abort.signal.aborted) setError("Nao foi possivel baixar. Verifique seu acesso e tente novamente."); }
    finally { if (session.isCurrent() && !abort.signal.aborted) setBusy(false); }
  };
  return <><Button type="button" variant="outline" disabled={disabled || busy} onClick={() => void download()}>{busy ? "Baixando arquivo..." : `Baixar ${file.filename}`}</Button>{error && <p role="alert" className="field-error">{error}</p>}</>;
}

export function LinkedAttachments({ files }: { files: readonly AttachmentSummary[] | undefined }) {
  return files?.length ? <ul className="attachment-links" aria-label="Arquivos registrados">{files.map(file => <li key={file.id}><span>{file.filename} <span className="record-meta">({file.bytes.toLocaleString("pt-BR")} bytes)</span></span><FileDownload file={file} /></li>)}</ul> : null;
}

export function IncomingAttachments({ files, caseId, blocked, refresh }: {
  files: IncomingFileSet | null | undefined; caseId: string; blocked: boolean; refresh: () => Promise<unknown>;
}) {
  const session = useWorkspaceSession();
  const api = createAttachmentApi(session.user.csrf_token, session.onAuthError);
  const request = useRef<AbortController | null>(null);
  useEffect(() => () => request.current?.abort(), []);
  const write = useTeamWrite(session, async (intent: RetryIntent) => {
    const abort = new AbortController(); request.current = abort;
    // Retain the original FILE version/key until its POST receipt AND a current
    // read confirm the same immutable case asset. A parent refresh is no ACK.
    const receipt = await api.retry(intent, abort.signal);
    try {
      const current = await api.get(receipt.attachment_id, abort.signal);
      if (current.id !== intent.id || current.owner_type !== "mail_case" || current.owner_id !== caseId || current.purpose !== "incoming" || current.version < receipt.version) throw Error("Incoming file identity not confirmed");
      return current;
    } catch (error) {
      if (error instanceof ApiError && [401, 403].includes(error.status)) throw error;
      throw Error("Current incoming file read not confirmed");
    }
  }, () => { void refresh().catch(() => {}); });
  // Hidden authority is not an empty set. Keep a pending intent private while
  // the mounted parent revalidates access; session disposal unmounts this owner.
  if (!files) return null;
  return <div className="attachment-picker" role="group" aria-label="Arquivos recebidos">
    <h3 className="work-subheading">Arquivos recebidos</h3>
    {files.status === "legacy" ? <p className="field-help">Os arquivos desta mensagem antiga nao foram processados. A ausencia de arquivos nesta tela nao confirma que a mensagem chegou sem anexos.</p> : files.status === "unavailable" ? <p className="read-notice">Nao foi possivel disponibilizar os arquivos desta mensagem. O texto recebido permanece disponivel; consulte o administrador.</p> : <>
      <p className="field-help">Arquivos originais da mensagem. O download depende da verificacao de seguranca e do seu acesso atual. Eles nao sao incluidos em respostas.</p>
      {files.items.length ? <ul className="attachment-list" aria-label="Arquivos originais recebidos">{files.items.map(file => <li className="attachment-row" key={file.id}>
        <div className="record-text"><span className="attachment-filename"><Paperclip size={16} aria-hidden="true" />{file.filename}</span><span className="record-meta">{file.bytes.toLocaleString("pt-BR")} bytes</span><span role="status" className="record-meta">{file.state === "ready" ? "Verificacao concluida" : stateLabels[file.state]}</span>{file.state === "ready" && !file.can_download && <p className="field-help">Download indisponivel nas condicoes atuais desta mensagem.</p>}</div>
        <div className="attachment-actions">{file.can_download && <FileDownload file={file} disabled={blocked || write.locked} />}{file.can_retry_scan && <Button type="button" variant="outline" disabled={blocked || write.locked} onClick={() => write.submit({ kind: "retry", id: file.id, version: file.version, key: crypto.randomUUID() })}>Verificar novamente {file.filename}</Button>}</div>
      </li>)}</ul> : <p>Nenhum arquivo recebido nesta mensagem.</p>}
    </>}
    {write.locked && <p role="status">{write.pending ? "Confirmando nova verificacao..." : "Verificacao sem resultado confirmado. A solicitacao original foi preservada."}</p>}
    {write.error && <div className="read-error"><p role="alert">{write.uncertain ? "Ainda nao foi possivel confirmar o resultado. Recupere a solicitacao original antes de tentar novamente." : writeError(write.error)}</p><div className="action-row">{(write.uncertain || isResourceForbidden(write.error)) && <Button type="button" variant="outline" disabled={write.pending} onClick={write.verify}>Recuperar verificacao original</Button>}{write.locked && !write.uncertain && write.error instanceof ApiError && write.error.status === 409 && <Button type="button" variant="outline" disabled={write.pending || write.reloading} onClick={() => void write.reconcile(async () => { await refresh(); })}>Atualizar e descartar tentativa recusada</Button>}</div></div>}
    {write.reloadFailed && <p role="alert" className="field-error">Nao foi possivel atualizar. A solicitacao original continua preservada.</p>}
    <Button type="button" variant="outline" disabled={blocked || write.pending} onClick={() => void refresh().catch(() => {} )}>Atualizar arquivos recebidos</Button>
  </div>;
}

export function AttachmentPicker({ scope, version, selected, change, disabled, busyChanged }: {
  scope: FileScope; version: number; selected: readonly AttachmentSummary[]; change: (files: AttachmentSummary[]) => void; disabled: boolean; busyChanged: (busy: boolean) => void;
}) {
  const session = useWorkspaceSession(), paging = usePaging(), inputId = useId();
  const api = createAttachmentApi(session.user.csrf_token, session.onAuthError);
  const query = useQuery({ queryKey: ["attachments", scope.owner, scope.id, scope.purpose, paging.cursor], queryFn: ({ signal }) => api.list(scope, paging.cursor, signal) });
  const [file, setFile] = useState<File | null>(null), [hashing, setHashing] = useState(false), [error, setError] = useState("");
  const request = useRef<AbortController | null>(null), reader = useRef<FileReader | null>(null);
  const live = useRef(true), selecting = useRef(false), input = useRef<HTMLInputElement | null>(null);
  useEffect(() => { live.current = true; return () => { live.current = false; request.current?.abort(); reader.current?.abort(); }; }, []);
  const write = useTeamWrite(session, async (intent: UploadIntent | RetryIntent) => {
    const abort = new AbortController(); request.current = abort;
    const receipt = intent.kind === "upload" ? await api.upload(scope, intent, abort.signal) : await api.retry(intent, abort.signal);
    // Replay first; a historical GET alone can never acknowledge the operation.
    try {
      const current = await api.get(receipt.attachment_id, abort.signal);
      if (current.id !== receipt.attachment_id || current.owner_type !== scope.owner || current.owner_id !== scope.id || current.purpose !== scope.purpose || current.version < receipt.version) throw Error("File identity not confirmed");
      if (intent.kind === "upload" && (current.filename !== intent.file.name || current.bytes !== intent.file.size || !("sha256" in receipt && "bytes" in receipt && "owner_type" in receipt && "owner_id" in receipt) || receipt.sha256 !== intent.digest || receipt.bytes !== intent.file.size || receipt.owner_type !== scope.owner || receipt.owner_id !== scope.id)) throw Error("Upload identity not confirmed");
      return current;
    } catch (error) {
      if (error instanceof ApiError && [401, 403].includes(error.status)) throw error;
      throw Error("Current file read not confirmed");
    }
  }, () => { if (live.current) { setFile(null); if (input.current) input.current.value = ""; setError(""); void query.refetch(); } });
  const busy = hashing || write.locked;
  useEffect(() => { busyChanged(busy); }, [busy, busyChanged]);
  const upload = async () => {
    if (!file || selecting.current || disabled || busy || !query.data?.can_upload || !session.isCurrent()) return;
    selecting.current = true; setHashing(true); setError("");
    const original = file, reviewedVersion = version;
    try {
      const buffer = await new Promise<ArrayBuffer>((resolve, reject) => {
        const source = new FileReader(); reader.current = source;
        source.onload = () => resolve(source.result as ArrayBuffer); source.onerror = source.onabort = () => reject(Error("File read interrupted")); source.readAsArrayBuffer(original);
      });
      if (!live.current || !session.isCurrent()) return;
      const digest = Array.from(new Uint8Array(await crypto.subtle.digest("SHA-256", buffer)), byte => byte.toString(16).padStart(2, "0")).join("");
      if (!live.current || !session.isCurrent()) return;
      write.submit({ kind: "upload", file: original, digest, version: reviewedVersion, key: crypto.randomUUID() });
    } catch { if (live.current && session.isCurrent()) setError("Nao foi possivel ler este arquivo. Selecione-o novamente."); }
    finally { selecting.current = false; if (live.current && session.isCurrent()) setHashing(false); }
  };
  const label = scopeLabels[scope.purpose];
  const content = (row: Attachment): ReactNode => <li className="attachment-row" key={row.id}>
    <div className="record-text"><span className="attachment-filename"><Paperclip size={16} aria-hidden="true" />{row.filename}</span><span className="record-meta">{row.bytes.toLocaleString("pt-BR")} bytes</span><span role="status" className="record-meta">{stateLabels[row.state]}</span></div>
    <div className="attachment-actions">{row.can_download && <FileDownload file={row} />}
      {query.data?.can_upload && <label className="work-checkbox"><input type="checkbox" checked={selected.some(file => file.id === row.id)} disabled={disabled || busy || query.isError || query.isFetching || row.state !== "ready" || (!selected.some(file => file.id === row.id) && selected.length >= 20)} onChange={event => change(event.target.checked ? [...selected, { id: row.id, filename: row.filename, media_type: row.media_type, bytes: row.bytes }] : selected.filter(file => file.id !== row.id))} />Incluir {row.filename}</label>}
      {row.can_retry_scan && <Button type="button" variant="outline" disabled={disabled || busy || query.isError || query.isFetching} onClick={() => write.submit({ kind: "retry", id: row.id, version: row.version, key: crypto.randomUUID() })}>Verificar novamente {row.filename}</Button>}
    </div></li>;
  return <div className="attachment-picker" role="group" aria-label={`Arquivos para ${label}`}>
    <h3 className="work-subheading">Arquivos para {label}</h3>
    <p className="field-help">{query.data?.can_upload ? "PDF, PNG, JPEG, TXT ou LOG, de 1 byte a 10 MiB por arquivo. Envie, aguarde a verificacao e marque os arquivos prontos que deseja incluir (ate 20). Enviar um arquivo nao registra texto nem envia e-mail." : "Consulte o estado dos arquivos e baixe os que estiverem disponiveis para sua conta."}</p>
    {query.data?.can_upload && <div className="attachment-upload"><label htmlFor={inputId}>Arquivo para {label}</label><input ref={input} id={inputId} type="file" accept=".pdf,.png,.jpg,.jpeg,.txt,.log" disabled={disabled || busy || query.isError} onChange={event => { const next = event.target.files?.[0] ?? null; setError(""); if (next && (next.size < 1 || next.size > 10485760)) { setFile(null); setError("Escolha um arquivo de 1 byte a 10 MiB."); } else setFile(next); }} /><Button type="button" variant="outline" disabled={disabled || busy || !file || query.isError || query.isFetching} onClick={() => void upload()}>Enviar arquivo para {label}</Button></div>}
    {busy && <p role="status">{hashing ? "Preparando arquivo..." : write.pending ? "Enviando ou confirmando arquivo..." : "Arquivo sem resultado confirmado. Recupere a operacao antes de continuar."}{file && ` ${file.name}`}</p>}
    {error && <p role="alert" className="field-error">{error}</p>}
    {write.error && <div className="read-error"><p role="alert">{write.uncertain ? "O resultado nao foi confirmado. O arquivo original foi mantido para recuperacao." : writeError(write.error)}</p><div className="action-row">{(write.uncertain || isResourceForbidden(write.error)) && <Button type="button" variant="outline" disabled={write.pending} onClick={write.verify}>Recuperar arquivo</Button>}{write.locked && <Button type="button" variant="outline" disabled={write.pending || write.reloading} onClick={() => void write.reconcile(async () => { await query.refetch({ throwOnError: true }); if (session.isCurrent()) setFile(null); })}>Recarregar e descartar operacao de arquivo</Button>}</div></div>}
    {write.reloadFailed && <p role="alert" className="field-error">A leitura falhou. O arquivo original continua retido.</p>}
    <Button type="button" variant="outline" disabled={query.isFetching} onClick={() => void query.refetch()}>Atualizar arquivos para {label}</Button>
    {query.isPending ? <LoadingRows label="Carregando arquivos..." /> : query.isError ? <ReadError retry={() => void query.refetch()}>Nao foi possivel consultar os arquivos. Verifique seu acesso e tente novamente.</ReadError> : <>{!query.data.can_upload && <p className="field-help">Acesso de consulta. Novos arquivos nao estao disponiveis nas condicoes atuais.</p>}{query.data.items.length ? <ul className="attachment-list" aria-label={`Arquivos de ${label}`}>{query.data.items.map(content)}</ul> : <p>Nenhum arquivo nesta pagina.</p>}<Paging paging={paging} next={query.data.next_cursor} label={`arquivos de ${label}`} disabled={query.isFetching} /></>}
    {!!selected.length && <AttachmentReview files={selected} />}
  </div>;
}
