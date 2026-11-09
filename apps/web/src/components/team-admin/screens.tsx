"use client";

import Link from "next/link";
import { IdentityBoundary, useWorkspaceSession } from "@/components/workspace-session";
import { createTeamApi } from "@/lib/teams";
import { TeamDirectory } from "./directory";
import { TeamDetail } from "./detail";

function Denied({ headingId }: { headingId: string }) {
  return <section className="working-surface access-surface"><h1 id={headingId} tabIndex={-1}>Acesso restrito</h1>
    <p className="intro">Sua conta não tem permissão para administrar equipes.</p>
    <Link className="text-link" href="/">Voltar à minha conta</Link></section>;
}

function DirectoryContent() {
  const session = useWorkspaceSession();
  return session.user.capabilities.includes("identity.manage")
      ? <TeamDirectory api={createTeamApi(session.user.csrf_token, session.onAuthError)} session={session} />
      : <Denied headingId="teams-heading" />;
}

function DetailContent({ id }: { id: string }) {
  const session = useWorkspaceSession();
  return session.user.capabilities.includes("identity.manage")
      ? <TeamDetail key={id} id={id} api={createTeamApi(session.user.csrf_token, session.onAuthError)} session={session} />
      : <Denied headingId="team-heading" />;
}

export function TeamDirectoryScreen() {
  return <IdentityBoundary location="Equipes" headingId="teams-heading" wide><DirectoryContent /></IdentityBoundary>;
}

export function TeamDetailScreen({ id }: { id: string }) {
  return <IdentityBoundary location="Equipes" headingId="team-heading" wide><DetailContent id={id} /></IdentityBoundary>;
}
