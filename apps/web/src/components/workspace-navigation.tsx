"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Building2, CheckCheck, FolderKanban, Inbox, Layers, Menu, Shapes, Ticket, UserRound, UsersRound, X, type LucideIcon } from "lucide-react";
import { useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { useWorkspaceSession } from "@/components/workspace-session";

type Destination = { href: string; label: string; icon: LucideIcon };
const work: Destination[] = [
  { href: "/my-work", label: "Meu trabalho", icon: CheckCheck },
  { href: "/projects", label: "Projetos", icon: FolderKanban },
  { href: "/clients", label: "Clientes", icon: Building2 },
];
const service: Destination[] = [
  { href: "/service-desk/tickets", label: "Chamados", icon: Ticket },
  { href: "/service-desk/mail-cases", label: "Mensagens recebidas", icon: Inbox },
  { href: "/service-desk/queues", label: "Filas de atendimento", icon: Layers },
];

// This component belongs to PrivateSession: its visibility, capabilities and
// lifetime follow the existing hidden/inert boundary and private query owner.
export function WorkspaceNavigation({ children }: { children: ReactNode }) {
  const { user } = useWorkspaceSession();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const navigation = useRef<HTMLElement>(null);
  const current = (href: string) => href === "/" ? pathname === "/"
    : pathname === href || pathname.startsWith(`${href}/`) || (href === "/my-work" && pathname.startsWith("/work-items/"));
  const links = (items: Destination[]) => items.map(({ href, label, icon: Icon }) =>
    <Link key={href} href={href} className="workspace-nav-link" aria-current={current(href) ? "page" : undefined}
      onClick={() => {
        setOpen(false);
        if (open && pathname === href) trigger.current?.focus();
      }}><Icon size={18} strokeWidth={1.7} aria-hidden="true" /><span>{label}</span></Link>);
  return <div className="workspace-frame" onKeyDown={event => {
    if (event.key === "Escape" && open) { event.preventDefault(); setOpen(false); trigger.current?.focus(); }
  }}>
    <Button ref={trigger} variant="ghost" className="navigation-toggle" aria-label="Navegacao principal"
      aria-expanded={open} aria-controls="workspace-navigation" onClick={() => {
        const next = !open; setOpen(next);
        if (next) requestAnimationFrame(() => navigation.current?.querySelector<HTMLAnchorElement>("a")?.focus());
      }}>{open ? <X size={20} aria-hidden="true" /> : <Menu size={20} aria-hidden="true" />}</Button>
    <nav ref={navigation} id="workspace-navigation" className={`workspace-navigation${open ? " is-open" : ""}`} aria-label="Navegacao principal">
      <div className="workspace-brand"><span className="brand-mark" aria-hidden="true">A</span><div>Altvia <span>Workspace</span></div></div>
      <div className="navigation-group">{links(work)}</div>
      <div className="navigation-group"><p>Service Desk</p>{links(service)}</div>
      <div className="navigation-group"><p>Organizacao</p>{links([{ href: "/operational-areas", label: "Areas operacionais", icon: Shapes }])}
        {user.capabilities.includes("identity.manage") && links([
          { href: "/admin/teams", label: "Administrar equipes", icon: UsersRound },
          { href: "/admin/users", label: "Administrar contas", icon: UserRound },
        ])}</div>
      <div className="navigation-account">{links([{ href: "/", label: "Minha conta", icon: UserRound }])}
        <span className="navigation-person">{user.display_name}</span></div>
    </nav>
    <div id="workspace-content" className="workspace-content" tabIndex={-1}>{children}</div>
  </div>;
}
