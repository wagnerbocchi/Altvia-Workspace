"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { QueryClientProvider, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Moon, Sun, ArrowRight, LoaderCircle } from "lucide-react";
import { useTheme } from "next-themes";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { createAppQueryClient } from "@/components/providers";
import { ApiError, currentUser, login, loginError, type CurrentUser } from "@/lib/auth";

const formSchema = z.object({
  email: z.email("Informe um e-mail válido.").trim().max(254, "Use até 254 caracteres."),
  password: z.string().min(1, "Informe sua senha.").max(1024, "Use até 1024 caracteres."),
});
const identityKey = ["current-user"] as const;

export type WorkspaceSession = {
  user: CurrentUser;
  isCurrent: () => boolean;
  onAuthError: (error: unknown) => void;
  onRefresh: () => void;
  onLogout: () => void;
};

const SessionContext = createContext<WorkspaceSession | null>(null);
export function useWorkspaceSession() {
  const session = useContext(SessionContext);
  if (!session) throw Error("Authenticated workspace session required");
  return session;
}

function sameSession(left: CurrentUser | null | undefined, right: CurrentUser) {
  return left?.id === right.id && left.csrf_token === right.csrf_token
    && [...left.capabilities].sort().join("|") === [...right.capabilities].sort().join("|");
}

function PrivateSession({ user, current, onAuthError, onRefresh, onLogout, children }: {
  user: CurrentUser; current: () => boolean; onAuthError: (error: unknown) => void;
  onRefresh: () => void; onLogout: () => void; children: ReactNode;
}) {
  const [client] = useState(createAppQueryClient);
  const live = useRef(true);
  useEffect(() => {
    live.current = true;
    return () => { live.current = false; client.clear(); };
  }, [client]);
  const isCurrent = () => live.current && current();
  return <QueryClientProvider client={client}><SessionContext.Provider value={{ user, isCurrent,
    onAuthError: error => { if (isCurrent()) onAuthError(error); },
    onRefresh: () => { if (isCurrent()) onRefresh(); },
    onLogout: () => { if (isCurrent()) onLogout(); },
  }}>{children}</SessionContext.Provider></QueryClientProvider>;
}

function ThemeToggle() {
  const { setTheme } = useTheme();
  // CSS media/theme rules choose the icon before hydration, without a flash.
  return <Button variant="ghost" className="theme-toggle" onClick={() => {
    setTheme(document.documentElement.classList.contains("dark") ? "light" : "dark");
  }} aria-label="Alternar tema claro e escuro">
    <Moon className="moon-icon" size={18} aria-hidden="true" />
    <Sun className="sun-icon" size={18} aria-hidden="true" /><span>Tema</span>
  </Button>;
}

function LoginForm({ onSuccess, notice }: { onSuccess: (user: CurrentUser) => void; notice: string }) {
  const [visible, setVisible] = useState(false);
  const form = useForm<z.infer<typeof formSchema>>({ resolver: zodResolver(formSchema), defaultValues: { email: "", password: "" } });
  const mutation = useMutation({ mutationFn: login, onSuccess(user) {
    form.reset(); onSuccess(user);
  }, onError() { form.setValue("password", ""); } });

  return <section className="working-surface" aria-labelledby="login-heading">
    <h1 id="login-heading" tabIndex={-1}>Acesse seu workspace</h1>
    <p className="intro">Use sua conta Altvia para entrar.</p>
    {notice && <p className="notice" role="status">{notice}</p>}
    <form noValidate onSubmit={form.handleSubmit(values => mutation.mutate(values))} aria-busy={mutation.isPending}>
      <div className="field">
        <label htmlFor="email">E-mail</label>
        <input id="email" type="email" autoComplete="username" inputMode="email" autoCapitalize="none" spellCheck={false}
          maxLength={254} placeholder="nome@empresa.com.br" {...form.register("email")}
          aria-invalid={!!form.formState.errors.email} aria-describedby={form.formState.errors.email ? "email-error" : undefined} />
        {form.formState.errors.email && <p id="email-error" className="field-error" role="alert">{form.formState.errors.email.message}</p>}
      </div>
      <div className="field">
        <label htmlFor="password">Senha</label>
        <div className="password-wrap">
          <input id="password" type={visible ? "text" : "password"} autoComplete="current-password" maxLength={1024}
            {...form.register("password")} aria-invalid={!!form.formState.errors.password}
            aria-describedby={form.formState.errors.password ? "password-error" : undefined} />
          <Button type="button" variant="ghost" className="reveal" onClick={() => setVisible(!visible)}
            aria-label={visible ? "Ocultar senha" : "Mostrar senha"} aria-pressed={visible}>
            {visible ? <EyeOff size={19} aria-hidden="true" /> : <Eye size={19} aria-hidden="true" />}
          </Button>
        </div>
        {form.formState.errors.password && <p id="password-error" className="field-error" role="alert">{form.formState.errors.password.message}</p>}
      </div>
      {mutation.isError && <p className="error-message" role="alert">{loginError(mutation.error)}</p>}
      <Button type="submit" className="submit" disabled={mutation.isPending}>
        {mutation.isPending ? <><LoaderCircle size={18} className="spinner" aria-hidden="true" /> Entrando...</>
          : <>Entrar <ArrowRight size={18} aria-hidden="true" /></>}
      </Button>
    </form>
    <p className="help">Precisa de acesso ou esqueceu a senha?<br />Procure o administrador da Altvia.</p>
  </section>;
}

export function IdentityBoundary({ children, location, headingId, wide = false }: {
  children: ReactNode; location: string; headingId: string; wide?: boolean;
}) {
  const client = useQueryClient();
  const previousUser = useRef(false);
  const [notice, setNotice] = useState("");
  const [challenge, setChallenge] = useState(false);
  const [checking, setChecking] = useState(false);
  const query = useQuery({ queryKey: identityKey, queryFn: async ({ signal }) => {
    const user = await currentUser(signal);
    if (user === null && previousUser.current) setNotice("Sua sessão terminou. Entre novamente.");
    return user;
  } });
  const authenticated = !!query.data && !query.isError;
  const view = query.isPending || checking ? "loading" : query.isError ? "connection"
    : !query.data ? "login" : challenge ? "challenge" : "content";
  const retainPrivate = !!query.data && !challenge
    && !(query.error instanceof ApiError && [401, 403].includes(query.error.status));
  useEffect(() => {
    const target = { login: "login-heading", content: headingId, connection: "connection-heading",
      challenge: "access-heading", loading: "" }[view];
    if (target) document.getElementById(target)?.focus();
    previousUser.current = authenticated;
  }, [authenticated, view, headingId]);
  const refresh = () => {
    setChecking(true);
    void query.refetch().then(result => { if (!result.isError) setChallenge(false); })
      .finally(() => setChecking(false));
  };
  return <div className="app-shell">
    <a className="skip-link" href="#main">Ir para o conteúdo</a>
    <header className="masthead"><div className="brand">Altvia <span>Workspace</span></div>
      <span className="location"><span className="location-dot" />{authenticated ? location : "Acesso"}</span>
      <ThemeToggle />
    </header>
    <main id="main" tabIndex={-1} className={wide && view === "content" ? "workspace-main" : undefined}>
      {view === "loading" ? <section className="working-surface state-surface" role="status"><LoaderCircle className="spinner" size={24} aria-hidden="true" /><p>Verificando acesso...</p></section>
        : view === "connection" ? <section className="working-surface" aria-labelledby="connection-heading">
          <h1 id="connection-heading" tabIndex={-1}>Conexão indisponível</h1><p className="intro" role="alert">Não foi possível verificar seu acesso. Confira sua conexão e tente novamente.</p>
          <Button onClick={refresh} disabled={query.isFetching}>{query.isFetching ? "Verificando..." : "Tentar novamente"}</Button>
        </section>
        : view === "challenge" ? <section className="working-surface" aria-labelledby="access-heading">
          <h1 id="access-heading" tabIndex={-1}>Verifique seu acesso</h1>
          <p className="intro" role="alert">Seu acesso precisa ser verificado antes de continuar. As alterações locais foram encerradas.</p>
          <Button onClick={refresh}>Verificar acesso</Button>
        </section>
        : view === "content" ? null
          : <LoginForm notice={notice} onSuccess={user => {
            client.setQueryData(identityKey, user); setNotice(""); setChallenge(false);
          }} />}
      {retainPrivate && query.data && <div hidden={view !== "content"} inert={view !== "content"}>
        <PrivateSession
          key={`${query.data.id}:${query.data.csrf_token}:${[...query.data.capabilities].sort().join("|")}`}
          user={query.data} current={() => sameSession(client.getQueryData<CurrentUser | null>(identityKey), query.data!)}
          onRefresh={refresh} onAuthError={error => {
            if (error instanceof ApiError && [401, 403].includes(error.status)) {
              setChallenge(true); void query.refetch();
            }
          }} onLogout={() => {
            previousUser.current = false; client.clear(); client.setQueryData(identityKey, null);
            setNotice("Você saiu da conta com segurança."); setChallenge(false);
          }}>{children}</PrivateSession>
      </div>}
    </main>
    <footer>Altvia Workspace <span>Ambiente interno</span></footer>
  </div>;
}
