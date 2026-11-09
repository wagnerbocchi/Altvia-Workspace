"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, LogOut, Moon, Sun, ArrowRight, LoaderCircle } from "lucide-react";
import { useTheme } from "next-themes";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { ApiError, currentUser, login, loginError, logout, type CurrentUser } from "@/lib/auth";

const formSchema = z.object({
  email: z.email("Informe um e-mail válido.").trim().max(254, "Use até 254 caracteres."),
  password: z.string().min(1, "Informe sua senha.").max(1024, "Use até 1024 caracteres."),
});
const identityKey = ["current-user"] as const;

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

function Account({ user, onLogout, onRefresh }: { user: CurrentUser; onLogout: () => void; onRefresh: () => void }) {
  const mutation = useMutation({ mutationFn: () => logout(user.csrf_token), onSuccess: onLogout,
    onError(error) { if (error instanceof ApiError && error.status === 403) onRefresh(); } });
  return <section className="working-surface" aria-labelledby="account-heading">
    <h1 id="account-heading" tabIndex={-1}>Minha conta</h1>
    <p className="intro">Você está conectado ao Altvia Workspace.</p>
    <dl className="account-details">
      <div><dt>Nome</dt><dd>{user.display_name}</dd></div>
      <div><dt>E-mail</dt><dd>{user.email}</dd></div>
    </dl>
    <div className="session-actions">
      {mutation.isError && <p className="error-message" role="alert">Não foi possível sair. Sua sessão pode continuar ativa. Tente novamente.</p>}
      <Button variant="outline" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
        {mutation.isPending ? <LoaderCircle size={18} className="spinner" aria-hidden="true" /> : <LogOut size={18} aria-hidden="true" />}
        {mutation.isPending ? "Saindo..." : "Sair da conta"}
      </Button>
    </div>
  </section>;
}

export function IdentityScreen() {
  const client = useQueryClient();
  const previousUser = useRef(false);
  const [notice, setNotice] = useState("");
  const query = useQuery({ queryKey: identityKey, queryFn: async ({ signal }) => {
    const user = await currentUser(signal);
    if (user === null && previousUser.current) setNotice("Sua sessão terminou. Entre novamente.");
    return user;
  } });
  const authenticated = !!query.data && !query.isError;
  const view = query.isPending ? "loading" : query.isError ? "connection" : query.data ? "account" : "login";

  useEffect(() => {
    const target = { login: "login-heading", account: "account-heading", connection: "connection-heading", loading: "" }[view];
    if (target) document.getElementById(target)?.focus();
    previousUser.current = authenticated;
  }, [authenticated, view]);

  return <div className="app-shell">
    <a className="skip-link" href="#main">Ir para o conteúdo</a>
    <header className="masthead"><div className="brand">Altvia <span>Workspace</span></div>
      <span className="location"><span className="location-dot" />{authenticated ? "Minha conta" : "Acesso"}</span>
      <ThemeToggle />
    </header>
    <main id="main" tabIndex={-1}>
      {query.isPending ? <section className="working-surface state-surface" role="status"><LoaderCircle className="spinner" size={24} aria-hidden="true" /><p>Verificando acesso...</p></section>
        : query.isError ? <section className="working-surface" aria-labelledby="connection-heading">
          <h1 id="connection-heading" tabIndex={-1}>Conexão indisponível</h1><p className="intro" role="alert">Não foi possível verificar seu acesso. Confira sua conexão e tente novamente.</p>
          <Button onClick={() => void query.refetch()} disabled={query.isFetching}>{query.isFetching ? "Verificando..." : "Tentar novamente"}</Button>
        </section>
        : query.data ? <Account user={query.data} onRefresh={() => void query.refetch()} onLogout={() => {
          previousUser.current = false;
          client.clear(); client.setQueryData(identityKey, null); setNotice("Você saiu da conta com segurança.");
        }} />
          : <LoginForm notice={notice} onSuccess={user => {
            client.setQueryData(identityKey, user); setNotice("");
          }} />}
    </main>
    <footer>Altvia Workspace <span>Ambiente interno</span></footer>
  </div>;
}
