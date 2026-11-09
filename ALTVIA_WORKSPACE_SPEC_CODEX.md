# ALTVIA WORKSPACE — ESPECIFICAÇÃO MESTRE PARA CODEX

**Versão:** 1.1  
**Data:** 2026-11-06  
**Tipo:** PRD + arquitetura + modelo de dados + requisitos de segurança + plano de entrega + instruções de implementação  
**Estado:** especificação para implementação; não representa funcionalidades já implementadas  
**Destinatário:** Codex operando no repositório de desenvolvimento da Altvia

> **Instrução principal ao Codex:** leia este documento integralmente e trate-o como fonte de requisitos do Altvia Workspace. Inspecione o repositório e a planilha original antes de criar código. Não tente entregar o sistema inteiro em uma única alteração. Comece pela Fase 0, registre decisões e implemente vertical slices testáveis nas fases posteriores. Não marque uma funcionalidade como concluída sem persistência real, autorização, testes e validação.

---

## 1. Produto, objetivos e restrições

**Nome:** Altvia Workspace. **Uso:** interno, self-hosted, voltado à operação da Altvia; não é um SaaS comercial ou produto para revenda. **Objetivo:** substituir a planilha de acompanhamento de atividades e centralizar projetos, tarefas, tickets/help desk, funcionários, SLAs, automações e gestão operacional em um único sistema.

A experiência de projetos deve ser **inspirada nos padrões de usabilidade do Plane** e a experiência de atendimento deve contemplar funcionalidades **semelhantes às do Zammad**. A aplicação será **100% independente**: não consumir APIs, banco ou serviços do Plane/Zammad, nem copiar código-fonte, assets, marcas ou componentes proprietários. Criar UI e identidade visual originais. O Zammad existente é apenas referência funcional; desativação/migração futura depende de aceite formal do novo Service Desk.

**Resultados de negócio obrigatórios:**

1. Colaborador visualiza, numa única fila, tickets e tarefas sob sua responsabilidade, sem dupla contagem quando relacionados.
2. Gestor visualiza trabalho por funcionário, equipe, cliente, projeto, prioridade, vencimento, bloqueio e status.
3. Ticket pode gerar automaticamente uma tarefa vinculada, de forma configurável e idempotente; também pode existir sem tarefa.
4. Tarefa pode existir sem ticket e pode estar relacionada a vários tickets; ticket pode possuir várias tarefas.
5. Comunicação de suporte por e-mail, filas, respostas, notas internas, anexos, histórico e SLA básico funcionam sem dependências externas de help desk.
6. Dashboards substituem as consolidações manuais do Excel, sem dados fictícios na produção.
7. Operação segura para informações e incidentes de clientes, com trilhas auditáveis.
8. Deploy compatível com o baseline de CPU **x86-64-v1**, conforme diagnóstico da VM-alvo abaixo.

**Fora de escopo do MVP:** billing, assinatura SaaS, marketplace, IA local/embeddings, cluster de busca externo, Gantt avançado, catálogo ITIL completo, CMDB avançada, portal de cliente com self-service completo e aplicativos móveis nativos. Registrar esses itens no backlog sem bloquear a entrega do MVP.

---

## 2. Evidência de origem: planilha operacional

**Arquivo obrigatório para análise e importação:** `Acompanhamento_Atividades_Altvia_Nov2026.xlsx`. Se não estiver no workspace do Codex, solicitar o arquivo antes de implementar o importador; não reconstruir dados reais com base neste resumo.

**Leitura confirmada em 2026-11-06:**

- Aba `Acompanhamento`: intervalo usado `A1:N35`, cabeçalho mais **34 atividades**.
- Colunas literais: `Responsável`, `Frente / Cliente`, `Atividade`, `Prioridade`, `Envolvidos`, `Status`, `Prazo de entrega`, `Dias restantes`, `Situação do prazo`, `Observações`, `Atividade da semana 1 `, `Atividade da semana 2`, `Atividade da semana 3`, `Atividade da semana 4 `.
- Aba `Resumo`: intervalo usado `A1:H16`, com agregação por responsável.
- Status encontrados: **Em andamento 14; Aguardando terceiros 8; A fazer 7; Concluído 4; Contínua 1**. O último valor é um caso especial: não o descartar nem classificá-lo automaticamente como `done`.
- Prioridades: **Média 21; Alta 9; Crítica 2; Baixa 2**.
- Resumo: **34 atividades, 20 sem prazo, 0 atrasadas** no estado salvo da planilha; os indicadores temporais devem ser recalculados com referência de data explícita ao migrar, pois fórmulas podem mudar com o tempo.
- Responsáveis agrupados no resumo: Neto (6), Rodolfo (7), Luiz Paulo (5), Eduardo Belmonte (3), Alexandre Violante (6) e Wagner Bocchi (7).
- A descrição da própria planilha indica que os status e prioridades iniciais foram inferidos da diária de 03/11/2026; não tratar esses valores como verdade imutável.

### 2.1 Mapeamento proposto

| Coluna de origem | Domínio/campo destino | Regra |
|---|---|---|
| Responsável | `work_items.owner_id` | Resolver nomes em `users`; ambiguidades vão para revisão, nunca criar usuários silenciosamente. |
| Frente / Cliente | `clients`, `projects`, `operational_areas` | São conceitos misturados: usar etapa de classificação humana com tabela de mapeamento versionada. |
| Atividade | `work_items.title`/`description` | Preservar texto original e linha de origem. |
| Prioridade | `work_items.priority` | Baixa→low; Média→medium; Alta→high; Crítica→critical. |
| Envolvidos | `work_item_assignees`/participantes externos | Resolver nomes; “Terceiro” não é automaticamente usuário interno. |
| Status | `work_items.status`, `work_items.work_type`, `blocked_reason` | A fazer→todo; Em andamento→in_progress; Aguardando terceiros→blocked + razão/external; Concluído→done; Contínua→recurring/ongoing **após decisão de modelo**. |
| Prazo de entrega | `work_items.due_at` | Converter datas Excel com timezone de negócio documentado; preservar ausência de prazo. |
| Dias restantes | calculado | Não persistir como fonte primária. |
| Situação do prazo | calculado | Distinguir overdue, due_soon, on_track, no_due_date, completed, ongoing. |
| Observações | comentário/nota de importação | Preservar conteúdo, origem e privacidade. |
| Atividade da semana 1–4 | `activity_events` ou updates históricos | Não inventar timestamps precisos ausentes; marcar período/coluna de origem. |

### 2.2 Importação e reconciliação

- Inspecionar fórmulas, validações, células vazias, datas seriais e textos originais. Gerar relatório de importação com contagens por status, responsável e prioridade.
- Criar `import_batches`, `import_rows`, `source_system`, `source_file_hash`, `source_sheet`, `source_row_number`, `original_payload`, `mapping_version`, `resolution_status`.
- Executar modo `dry-run` antes de gravar. A importação real deve ser idempotente, transacional por lote lógico e reproduzível.
- Nunca preencher prazos ausentes, inventar vínculos com tickets ou converter “Contínua” sem regra aprovada.
- Reportar linhas ambíguas, nomes não resolvidos, vínculos externos e divergências de indicadores. Preservar fonte original.

---

## 3. Público, acesso e políticas

**Papéis iniciais:** `platform_admin` (configuração global), `operations_manager` (visão gerencial de equipes permitidas), `project_manager` (gestão dos projetos autorizados), `agent` (atendimento/tarefas), `viewer` (somente leitura conforme escopo). Contatos externos não recebem acesso ao portal no MVP; suas identidades são registradas para e-mail/solicitante.

**Autorização:** sempre no backend, por ação **e** recurso. Definir escopos `client_id`, `project_id`, `team_id` e `ticket_queue_id` conforme domínio. Não assumir que um gestor pode ver todos os clientes. Notas internas e anexos têm restrições próprias. Testar BOLA/IDOR em ticket, mensagem, anexo, tarefa e vínculo cruzado. Privacidade e retenção compatíveis com política interna e LGPD; definir prazo de retenção com a gestão antes da produção.

---

## 4. Requisitos funcionais e critérios de aceite

| ID | Capacidade | Prioridade | Critério observável |
|---|---|---|---|
| FR-001 | Login, sessão, usuários, equipes, RBAC | P0 | Usuário não autorizado não lê nem altera dados de outro escopo; sessões expiram/revogam. |
| FR-002 | Clientes, áreas e projetos | P0 | CRUD com permissões; cliente pode conter múltiplos projetos. |
| FR-003 | Tarefas/subtarefas e responsáveis | P0 | Criar, editar, atribuir e concluir; suportar owner + envolvidos. |
| FR-004 | Kanban, lista, filtros, busca e My Work | P0 | Dados reais, paginação, filtros, estados vazios e erros. |
| FR-005 | Tickets, filas, categorias e histórico | P0 | Ticket recebe número único, requester, atribuição, status, prioridade e trilha de eventos. |
| FR-006 | Respostas, notas internas e anexos | P0 | Mensagens ordenadas, ACL de notas e download protegido. |
| FR-007 | E-mail inbound/outbound | P0 | Receber nova solicitação, correlacionar respostas com segurança e responder preservando thread. |
| FR-008 | Ticket ↔ work item | P0 | Associação N:N validada, sem misturar status e SLAs. |
| FR-009 | Atribuição gera trabalho por regra | P0 | Um evento reprocessado não duplica tarefa; owner/projeto resolvidos. |
| FR-010 | Dashboard operacional | P0 | Indicadores por usuário/cliente/projeto/ticket, sem hardcode. |
| FR-011 | SLA básico | P0 | Primeira resposta e resolução com calendário/pausas e eventos de violação. |
| FR-012 | Auditoria e activity timeline | P0 | Ator, ação, recurso, data, alterações relevantes e correlação. |
| FR-013 | Notificações | P1 | Atribuição, menções, bloqueios, atraso e SLA, com preferências. |
| FR-014 | Time tracking | P1 | Apontamento por tarefa/ticket, totalização e permissão. |
| FR-015 | Exportação CSV/XLSX | P1 | Exportar somente dados autorizados, sanitizando fórmulas de planilha. |
| FR-016 | Calendário/Gantt/dependências avançadas | P2 | Backlog, após estabilização do fluxo básico. |
| FR-017 | Portal externo/base de conhecimento | P2 | Backlog, não pré-requisito do MVP. |

### 4.1 Status separados por domínio

- **Work Item:** `todo`, `in_progress`, `blocked`, `done`, `cancelled`; modelar trabalho contínuo/recorrente sem forçar `done`.
- **Ticket:** `new`, `open`, `pending_customer`, `pending_third_party`, `resolved`, `closed`.
- Motivos de bloqueio, pendências e pausa de SLA são campos/eventos explícitos; estado visual não substitui histórico.
- A transição `resolved` → `closed` e reabertura devem ser configuráveis e auditáveis.

### 4.2 Políticas de fluxo

1. Ticket não cria tarefa obrigatoriamente. `automation_rules` decide quando criar ou vincular.
2. Em `ticket.assigned`, resolver `client_default_project` e responsável; se não houver projeto adequado, gerar evento de triagem, não criar projeto fictício.
3. Linkar tarefas existentes quando apropriado, evitando duplicação de atividade na fila unificada.
4. Reatribuir ticket não apaga executor histórico nem altera automaticamente a propriedade de tarefa já em progresso sem regra específica.
5. Fechar ticket não conclui automaticamente todas as tarefas; a regra de sincronização deve ser explícita.
6. Reabrir ticket não deve criar duplicação; concorrência e retries devem ser testados.
7. Solicitantes externos não podem ler comentários internos.
8. SLA de ticket e prazo de tarefa são conceitos distintos.

---

## 5. Arquitetura de referência

**Estilo:** modular monolith, sem microservices e sem Kubernetes no MVP.

| Camada | Escolha inicial | Observações |
|---|---|---|
| Frontend | Next.js + TypeScript strict | UI original, responsiva, acessível; SSR/CSR conforme necessidade. |
| Componentes | Tailwind CSS + shadcn/ui | React Hook Form + Zod; TanStack Query; dark/light mode. |
| API | Python + FastAPI + Pydantic | OpenAPI, schemas tipados, versionamento `/api/v1`. |
| Persistência | PostgreSQL + SQLAlchemy 2 + Alembic | FKs, constraints, transações e índices. |
| Fila/cache | Redis + worker Python | Selecionar biblioteca de jobs mantida, compatível com CPU baseline. |
| Eventos | Transactional Outbox em PostgreSQL | `at least once`, consumer idempotente, retry e DLQ lógica. |
| Arquivos | S3-compatible object storage | Buckets privados, streaming protegido, validação de uploads. |
| Email | IMAP/SMTP adapters | MIME, correlação segura, idempotência e entrega resiliente. |
| Auth | Local segura inicialmente; interface OIDC | Argon2id, sessão revogável, cookies seguros; MFA via IdP quando disponível. |
| Busca | PostgreSQL FTS + GIN; `pg_trgm` se validado | Sem Elasticsearch/OpenSearch/Solr/MongoDB no MVP. |
| Observabilidade | JSON logs + métricas + healthchecks | OpenTelemetry/Prometheus/Grafana opcionais conforme infraestrutura. |
| Deploy | Docker Compose + proxy HTTPS | Segredos externos, redes isoladas, backups e restore. |

### 5.1 Estrutura sugerida

```text
altvia-workspace/
├── AGENTS.md                         # Instruções persistentes ao Codex, referenciando este documento
├── ALTVIA_WORKSPACE_SPEC_CODEX.md    # Este documento
├── apps/
│   ├── web/                          # Next.js
│   ├── api/
│   │   ├── app/
│   │   │   ├── core/                  # auth, config, security, errors
│   │   │   ├── modules/
│   │   │   │   ├── identity/
│   │   │   │   ├── clients/
│   │   │   │   ├── teams/
│   │   │   │   ├── projects/
│   │   │   │   ├── work_items/
│   │   │   │   ├── tickets/
│   │   │   │   ├── email/
│   │   │   │   ├── sla/
│   │   │   │   ├── automation/
│   │   │   │   ├── analytics/
│   │   │   │   ├── notifications/
│   │   │   │   └── audit/
│   │   │   └── infrastructure/       # db, storage, transport, queues
│   │   ├── migrations/
│   │   └── tests/
│   └── worker/
├── packages/
│   ├── ui/
│   └── contracts/
├── infra/
├── scripts/
└── docs/
    ├── prd/
    ├── architecture/
    ├── adr/
    ├── runbooks/
    └── roadmap.md
```

Criar apenas diretórios necessários a cada fase. Não duplicar regras de negócio entre módulos. Sem endpoints que acessam tabelas de outro domínio ignorando interfaces/políticas. Separar DTOs, domínio e persistência onde houver benefício concreto, evitando abstração excessiva.

---

## 6. Modelo de dados — entidades e invariantes

**Identidade:** `users`, `teams`, `team_members`, `roles`, `permissions`, `role_permissions`, `sessions`.  
**Clientes:** `clients`, `client_contacts`, `client_services` (serviços pós-MVP se não essenciais).  
**Projetos:** `projects`, `project_members`, `project_milestones`.  
**Trabalho:** `work_items`, `work_item_assignees`, `work_item_dependencies`, `work_item_comments`, `work_item_status_history`, `time_entries`.  
**Help desk:** `ticket_queues`, `ticket_categories`, `tickets`, `ticket_messages`, `ticket_participants`, `ticket_status_history`, `ticket_work_items`.  
**SLA:** `sla_policies`, `ticket_sla_states`, `business_calendars`, `holidays`.  
**Infra:** `attachments`, `attachment_links`, `mailboxes`, `inbound_messages`, `outbound_messages`.  
**Automação/auditoria:** `automation_rules`, `automation_executions`, `outbox_events`, `processed_events`, `activity_events`, `audit_logs`, `notifications`.  
**Importação:** `import_batches`, `import_rows`.

### 6.1 Campos mínimos

**`work_items`:** `id UUID`, `project_id`, `parent_id nullable`, `owner_id nullable`, `title`, `description`, `status`, `work_type`, `priority`, `due_at nullable`, `started_at`, `completed_at`, `blocked_reason`, `estimated_minutes`, `created_at`, `updated_at`, `version`. Participantes em tabela N:N. O campo `work_type` ou conceito equivalente distinguirá atividade pontual e contínua/recorrente, conforme ADR de modelagem da planilha. Impedir ciclos de subtarefas e dependências.

**`tickets`:** `id UUID`, `number BIGINT UNIQUE`, `client_id`, `requester_id`, `queue_id`, `assignee_id nullable`, `subject`, `description`, `status`, `priority`, `source`, `sla_policy_id`, `first_response_at`, `resolved_at`, `closed_at`, `created_at`, `updated_at`, `version`.

**`ticket_messages`:** `ticket_id`, `author_id/contact_id`, `direction`, `visibility` (public/internal), `body_text`, `body_html_sanitized`, `message_id`, `received_at/sent_at`, `delivery_status`. ACL rigorosa.

**`ticket_work_items`:** PK composta `(ticket_id, work_item_id)`, `relation_type`, `created_at`, `created_by`. Verificar autorização de **ambos** os objetos antes de criar vínculo; avaliar cliente/projeto cruzado conforme política.

**`outbox_events`:** `event_id`, `aggregate_type`, `aggregate_id`, `event_type`, `payload`, `occurred_at`, `status`, `attempts`, `next_attempt_at`. Registrar deduplicação por idempotency key lógica em `processed_events`/`automation_executions`.

Todas as FKs, `CHECK`, unicidades, índices de consultas e limites devem ser definidos em migrations reais. UUIDs de exemplos não são valores válidos para fixtures; gerar UUIDs concretos em testes. Usar `TIMESTAMPTZ` e persistir instantes em UTC, com exibição pelo timezone configurado. `version` para controle de concorrência quando necessário.

### 6.2 Consultas e desempenho

- Paginação server-side; cursor quando adequado; evitar N+1 e filtros sem índice.
- Busca com PostgreSQL `to_tsvector`/`websearch_to_tsquery` ou APIs equivalentes; índices GIN e, se necessário, extensão `pg_trgm` habilitada com migration.
- Aplicar autorização **antes** de devolver resultados de busca; indexação não pode contornar escopo de cliente.
- Criar visões/queries agregadas para dashboard com benchmarks sobre dados de teste representativos; não persistir contagens duplicadas sem justificação.

---

## 7. UX e telas

Design original da Altvia, inspirado na densidade e navegabilidade do Plane: sidebar fixa, navegação contextual, busca global, quick actions, breadcrumbs, acessibilidade, atalhos de teclado quando pertinentes, responsividade e dark/light mode. Nunca copiar logos/branding/assets ou reproduzir telas de forma literal.

**Navegação:** Overview; My Work; Projects; Service Desk; Team; Planning; Analytics; Settings.

**Overview:** contadores reais de tickets, tarefas, vencimentos, bloqueios e SLAs; recortes por equipe e cliente.  
**My Work:** fila unificada de tickets e work items, com identificação de origem, prioridade, estado, prazo e vínculo; sem dupla contagem.  
**Projects:** lista de projetos, Kanban, tabela, detalhes, membros, marcos e progresso.  
**Service Desk:** inbox com filas, filtros, SLA, conversa, notas internas, anexos e painel de trabalho vinculado.  
**Team:** carga por colaborador, bloqueios, atividades sem prazo e capacidade; não ranquear produtividade apenas por tickets fechados.  
**Analytics:** métricas persistidas, filtros por data, cliente, equipe, projeto e responsável.  
**Settings:** usuários/papéis, clientes, filas, SLAs, mailboxes, automações e auditoria.

**Qualidade UI:** loading/empty/error/success states, skeletons quando úteis, navegação por teclado, labels, foco visível, contraste, feedback de mutações, confirmação de operações destrutivas. Sem botões decorativos ou dashboards com números hardcoded.

---

## 8. Fluxos críticos

### 8.1 Ticket → tarefa

1. Ticket chega por e-mail, API ou cadastro manual.
2. Classificação atribui cliente, categoria, fila, prioridade e técnico.
3. Alteração do ticket e evento `ticket.assigned` são gravados **na mesma transação**.
4. Worker lê outbox, avalia regras estruturadas e resolve projeto/owner.
5. Se não existir vínculo lógico, cria work item e `ticket_work_items` em transação protegida por unicidade/idempotência.
6. `My Work` apresenta tarefa e ticket relacionados sem duplicação de esforço.
7. Reabertura, reassignment, retries e falhas são processados sem perda de evento ou duplicação.

Exemplo de regra validada por schema (não permitir script arbitrário):

```json
{
  "name": "Criar tarefa ao atribuir ticket de infraestrutura",
  "enabled": true,
  "trigger": "ticket.assigned",
  "conditions": {
    "queues": ["infrastructure", "cloud"],
    "assignee_required": true
  },
  "actions": [{
    "type": "work_item.create_or_link",
    "project_strategy": "client_default_project",
    "assign_to": "ticket.assignee",
    "copy_priority": true,
    "copy_due_date": false
  }]
}
```

Eventos iniciais: `ticket.created`, `ticket.assigned`, `ticket.status_changed`, `ticket.message_received`, `work_item.created`, `work_item.assigned`, `work_item.blocked`, `work_item.completed`, `sla.breached`. Ações: criar/vincular tarefa, atribuir, notificar, escalonar, registrar eventos. Implementar retries com backoff, dead-letter lógica, alertas e observabilidade.

### 8.2 Ticket por e-mail

- IMAP/SMTP seguros configurados por mailbox e credenciais externas ao código.
- Parsing MIME, limites de tamanho, text fallback, sanitização de HTML, anexos privados e varredura de arquivo conforme decisão de infra/CPU.
- Correlação por `Message-ID`, `In-Reply-To`, `References` e identificador interno com checagem de identidade/escopo; **nunca apenas subject**.
- Deduplicação de mensagens, tratamento de mensagens malformadas, origem não confiável, controle de `From`/`Reply-To`, retries de envio e status de entrega.
- Distinguir nota interna de resposta pública; prevenir envio acidental de dados internos para cliente.

### 8.3 SLA

- SLA de primeira resposta e resolução, políticas por cliente/categoria/prioridade, calendários comerciais, feriados e timezone.
- Estados de pausa configuráveis com histórico e regras explícitas; alteração de SLA não reescreve silenciosamente o histórico.
- Workers calculam aproximação/violação com testes de limites, virada de dia, feriado, horário de verão quando aplicável e reabertura.

### 8.4 Atividade de projeto

- Gestor cria projeto e tarefas, define owners, participantes e marcos.
- Colaborador atualiza estado, registra comentários, bloqueios, esforço e evidências.
- Dashboard exibe responsável, projeto, prazo, blocked reason, atividade recente e progresso sem intervenção manual.

---

## 9. API e contratos

API versionada: `/api/v1`, OpenAPI gerada a partir de schemas tipados, tratamento consistente de erros, status HTTP corretos, filtros validados, autorização por recurso, paginação, idempotência e concorrência otimista.

| Método | Rota | Uso |
|---|---|---|
| GET/POST | `/clients` | Consultar/criar clientes |
| GET/POST | `/projects` | Consultar/criar projetos |
| GET/POST | `/work-items` | Consultar/criar tarefas |
| PATCH | `/work-items/{id}` | Atualizar com proteção de concorrência |
| GET | `/my-work` | Trabalho consolidado do usuário autenticado |
| GET/POST | `/tickets` | Consultar/criar tickets |
| PATCH | `/tickets/{id}` | Atualizar ticket |
| POST | `/tickets/{id}/messages` | Resposta/nota |
| POST | `/tickets/{id}/work-items` | Criar ou vincular tarefa |
| GET | `/analytics/overview` | Dashboard agregado autorizado |
| GET | `/analytics/team-workload` | Carga da equipe autorizada |

Mutações críticas devem aceitar `Idempotency-Key` com armazenamento persistido. `201` para criação, `200` para vínculo existente/replay quando aplicável, `409` para conflito de estado/versão, `422` para payload inválido, `401/403/404` conforme autenticação e autorização. Não expor detalhes de outros clientes em erros. Tipos/contratos compartilhados devem ser gerados ou verificados, não copiados manualmente sem testes de compatibilidade.

---

## 10. Segurança e compliance — critérios mandatórios

- Autenticação: Argon2id para credenciais locais, política segura de sessão, cookie `HttpOnly`, `Secure`, `SameSite`, proteção CSRF quando aplicável, revogação, rate limiting, MFA via OIDC/IdP quando disponível.
- RBAC + verificação por recurso em todas as operações, buscas, eventos e downloads. Testes explícitos de BOLA/IDOR e escopo cruzado.
- Queries parametrizadas, validação de entrada, proteção XSS, CSRF, SSRF, path traversal, command injection, insecure deserialization e privilege escalation.
- Uploads: tamanhos/tipos permitidos, armazenamento fora do webroot, URLs temporárias e autorizadas, política de malware scanning compatível com CPU/infra.
- E-mail HTML como entrada hostil; sanitização e CSP. Anexos com ACL e logs sem payload sensível.
- Logs estruturados com request/correlation IDs e sem senhas, tokens ou conteúdo sensível de tickets; trilha auditável para ação e ator.
- Secrets via secret manager/arquivos de segredo com permissões, nunca commitados. `.env.example` com placeholders.
- Banco/Redis/Object Storage não publicados na internet; TLS no proxy, backups criptografados e restore testado.
- CI: SAST, SCA, secret scanning, container scanning, testes e bloqueio de merge por falhas críticas.
- Política de retenção de tickets, e-mails e anexos sujeita a aprovação da empresa; não presumir prazo legal universal.

**Ameaças prioritárias:** BOLA/IDOR (crítica), stored XSS por e-mail/ticket (alta), exfiltração por anexos (alta), spoofing/correlação indevida de mensagens (alta), duplicação por race conditions (alta). A severidade final depende de análise contextual.

---

## 11. RESTRIÇÃO DE INFRAESTRUTURA E CPU — OBRIGATÓRIO

### 11.1 Ambiente informado e observado

VM Ubuntu **24.04.5 LTS**, arquitetura `x86_64`, **12 vCPUs**, virtualizador **KVM/QEMU**, CPU apresentada ao guest como **`QEMU Virtual CPU version 2.5+`**. BIOS virtual indica modelo RHEL 7.6/i440FX. Saída `lscpu` indica `sse`, `sse2`, `pni` (SSE3), `cx16`, `nx`, mas **não** inclui `ssse3`, `sse4_1`, `sse4_2`, `avx`, `avx2`, `fma` ou `bmi2`.

**Conclusão técnica:** o guest está limitado aproximadamente ao baseline **x86-64-v1**. Não inferir a CPU física nem afirmar que o host não suporta instruções modernas. A VM pode ocultá-las. Modelo de hypervisor/CPU só poderá ser ajustado pelo administrador do host, considerando live migration e rollback.

### 11.2 Regra de compatibilidade

**Nenhum serviço obrigatório do MVP pode exigir AVX, AVX2, AVX-512, SSE4.2, FMA, BMI2 ou x86-64-v2/v3/v4.** Este é um requisito de aceitação de deployment até que a equipe valide e autorize mudança do modelo de CPU virtual.

**Proibido introduzir no MVP sem ADR/autorização:** Elasticsearch, OpenSearch, Solr, MongoDB, bancos vetoriais e runtimes locais de IA/embedding, ou binários que exijam ISA superior ao guest. Não instalar search engine externo; usar **PostgreSQL Full Text Search** + índices GIN e, se compatível, extensão `pg_trgm`.

A proibição nominal é uma política de arquitetura, não a afirmação de que todas as versões desses produtos sempre exigem AVX. A compatibilidade real é **por versão, imagem e build**, não apenas por nome do software.

Verificar também quaisquer dependências nativas de Node/Python, wheel, biblioteca de imagens, parser, antivírus, compressão, banco, storage e versões de glibc. **Não usar `-march=native`** em imagens portáveis. Pinning de versões/digests de container no deployment. Não presumir compatibilidade apenas porque `docker pull` teve sucesso.

### 11.3 Diagnóstico reproduzível no guest

```bash
uname -m
lscpu
lscpu | grep -E 'Architecture|Model name|CPU\(s\)|Hypervisor'
grep -m1 '^flags' /proc/cpuinfo | tr ' ' '\n' \
  | grep -E '^(sse2|pni|ssse3|sse4_1|sse4_2|avx|avx2|fma|bmi2)$' || true
```

### 11.4 Smoke test obrigatório de runtime na VM

Antes de fixar a stack, usar tags/digests aprovadas no ADR de compatibilidade e executar **no host-alvo** smoke tests de runtime e inicialização de serviços; por exemplo:

```bash
docker run --rm --entrypoint node node:24-bookworm-slim -v
docker run --rm --entrypoint python python:3.12-slim python -V
docker run --rm --entrypoint postgres postgres:17 postgres --version
docker run --rm --entrypoint redis redis:7 redis-server --version
```

**Observação:** tags acima são referências iniciais de teste, não homologação nem garantia de compatibilidade/segurança. Verificar versões suportadas e vulnerabilidades na data do build e depois travar por digest. Se qualquer container produzir `Illegal instruction`, investigar binário e ISA efetiva, selecionar build compatível e documentar o resultado; nunca mascarar erro ou desativar healthcheck.

Além de `--version`, iniciar PostgreSQL, Redis, API, web e worker e executar transação, query FTS, enqueue/dequeue, upload e E2E completo. Rodar a mesma imagem do ambiente de produção. Validar uso real da CPU e memória com carga representativa.

### 11.5 Gate de CPU antes de produção

- [ ] Flags capturadas do guest e registradas no ADR.
- [ ] Manifesto de imagens e digests aprovado.
- [ ] Todas as imagens inicializam sem SIGILL/`Illegal instruction`.
- [ ] Bibliotecas nativas de produção testadas na VM real.
- [ ] `postgres`/`redis`/worker/frontend/API passam smoke test funcional.
- [ ] PostgreSQL FTS testado sem search engine externo.
- [ ] Backups e restore testados no mesmo baseline.
- [ ] Sem dependências AVX/SSE4.2 não homologadas.
- [ ] Restrições e evidências documentadas em `docs/architecture/infrastructure-compatibility.md`.

---

## 12. Requisitos não funcionais, observabilidade e operação

- Métricas alvo **propostas**, sujeitas a benchmark: p95 de leitura paginada usual <500 ms, disponibilidade operacional alvo 99,5%, RPO até 24 h e RTO até 4 h. Não prometer metas sem medir recursos de CPU, RAM, disco e carga.
- Health/readiness endpoints, métricas de fila e job, logs JSON com correlation ID, monitoramento de falha de e-mail, automação e breach de SLA.
- Docker Compose com `web`, `api`, `worker`, `postgres`, `redis`, `object-storage` se necessário e `reverse-proxy`; sem exposição pública de serviços internos.
- Dockerfiles multi-stage quando aplicável, usuários não root, permissões de volumes, resource limits, restart policies e secret injection.
- Documentar setup dev/prod, migrations, rollback de deploy, backup e restauração; deploy somente com plano de rollback e checklist pós-mudança.
- Backups devem cobrir banco, anexos e configurações críticas; restauração precisa validar consistência entre banco e storage.

---

## 13. Testes e definição de pronto

**Backend:** unitários de domínio, integrações com PostgreSQL, API, autorização, constraints, migrations, concorrência e idempotência.  
**Frontend:** componentes, validação de formulário, navegabilidade, estados de erro/vazio e type checking.  
**E2E:** login; cliente; projeto; tarefa/subtarefa; atribuição; ticket; mensagem; anexo privado; recebimento de e-mail; vinculação automática; My Work; dashboard; SLA; fechamento/reabertura.  
**Security tests:** IDOR cross-client; acesso de nota/anexo não autorizado; ticket↔work item cross-scope; email forged/malformed; HTML inseguro; retry duplicado; concorrência; transição inválida.  
**CPU/deploy tests:** runtime no x86-64-v1 efetivo da VM-alvo, sem instrução ilegal, sem Elasticsearch.

**DoD por funcionalidade:** schema/migration (se aplicável), serviço de domínio, endpoint tipado, autorização, UI com dados reais, tratamento de erro, testes executados, documentação/ADR atualizados e evidência de funcionamento. Não considerar dashboard mockado ou botão inerte como funcionalidade pronta. Não afirmar execução de testes sem logs/comandos reais.

**Checklist de validação pós-deploy:**

1. Services healthy; sem SIGILL; consumo CPU/RAM/IO aceitável.
2. Migrations corretas e integridade referencial consistente.
3. Login/sessões e RBAC autorizam e negam casos esperados.
4. CRUD de cliente/projeto/tarefa/ticket persiste após restart.
5. E-mail inbound/outbound cria e atualiza thread corretamente.
6. `ticket.assigned` cria/vincula tarefa exatamente uma vez sob retries.
7. My Work e analytics refletem dados reais e respeitam ACL.
8. SLA calcula janelas e pauses adequadamente.
9. Anexos privados não podem ser obtidos por usuário não autorizado.
10. Backup e recuperação verificados; rollback documentado.

---

## 14. Roadmap de implementação incremental

**Fase 0 — Discovery, PRD e decisões (somente documentação e análise)**
- Inspecionar repositório, ferramentas disponíveis e planilha completa.
- Conferir todos os dados de origem, divergências e status `Contínua`.
- Consolidar PRD, matriz RBAC, ERD, ADR de modular monolith, ADR de CPU x86-64-v1, ADR de autenticação, outbox e e-mail.
- Especificar API, migrations planejadas, critérios de aceite, dependências e milestones.
- **Gate:** documentação revisável, escopo claro, ambiguidades explicitadas. Não gerar centenas de arquivos nesta fase.

**Fase 1 — Foundation e identidade**
- Scaffold web/API/worker e Compose; Postgres/Redis, migrations, config e CI.
- Auth local segura (com interface para OIDC), sessões, RBAC, usuários e equipes.
- Validar compatibilidade de CPU dos binários selecionados **na VM-alvo**.
- **Gate:** login, RBAC, API e banco funcionais, migrations reproduzíveis, testes passados.

**Fase 2 — Clientes, projetos e trabalho**
- Clientes, projetos, membros, tarefas, subtarefas, owner/assignees, comentários, prazos, bloqueios e histórico.
- Kanban, lista e My Work (tarefas); filtros e busca.
- **Gate:** um projeto e suas tarefas podem ser operados integralmente sem dados simulados.

**Fase 3 — Service Desk nativo**
- Filas, categorias, tickets, atribuição, status, conversa, notas internas, anexos, pesquisa e histórico.
- IMAP/SMTP e correlação segura de mensagens.
- **Gate:** solicitação por e-mail é recebida, respondida, reaberta e fechada com trilha íntegra.

**Fase 4 — Trabalho unificado e automações**
- Relação N:N ticket↔work item, regras estruturadas, outbox, worker, retry, DLQ, idempotência.
- Consolidar My Work sem dupla contagem e autorizar vínculos corretamente.
- **Gate:** atribuição gera tarefa conforme regra exatamente uma vez e suporta race/replay/reopen.

**Fase 5 — SLA, analytics e importação**
- Calendários, políticas SLA, breach, notificações e dashboards por funcionário/equipe/cliente/projeto.
- Importador com dry-run, mapeamento, reconciliação da planilha e relatórios.
- **Gate:** gestores obtêm métricas da planilha diretamente no sistema; divergências explicadas.

**Fase 6 — Hardening e readiness**
- E2E, pentest direcionado, profiling de queries, observabilidade, auditoria de containers, backup/restore, runbooks, implantação piloto.
- **Gate:** checklist de produção aprovado e processo de rollback documentado.

**Execução:** preferir uma feature vertical completa por PR/commit lógico, com testes. Nada de avançar visualmente 3 fases sem domínio/API por trás. Se a Fase 3 não estiver pronta, não declarar substituição do Zammad.

---

## 15. Comandos de execução sugeridos ao Codex

**Primeiro comando (utilizar após incluir este documento e a planilha no workspace):**

> Leia `ALTVIA_WORKSPACE_SPEC_CODEX.md` e analise integralmente `Acompanhamento_Atividades_Altvia_Nov2026.xlsx`. Execute **somente a Fase 0**. Inspecione o repositório antes de editar. Produza PRD revisado, ERD, matriz RBAC, ADRs, contratos iniciais e roadmap com critérios verificáveis. Registre o baseline da VM Ubuntu 24.04.5 KVM/QEMU x86-64-v1 sem SSE4.2/AVX/AVX2, incluindo o plano de testes de compatibilidade de containers. Não implemente o sistema ainda e não invente dados/validações.

**Início da implementação, após revisar a Fase 0:**

> Siga `ALTVIA_WORKSPACE_SPEC_CODEX.md` e os ADRs aprovados. Implemente apenas a próxima vertical slice da Fase 1. Inclua testes, migrations e documentação quando aplicável. Execute build, lint, typecheck e testes no ambiente disponível; se não puder executar algo, explique o impedimento. Ao terminar, liste arquivos alterados, comportamento, resultados e pendências. Não avance para a fase seguinte sem cumprir o gate atual.

**Comando padrão para cada fase posterior:**

> Consulte a especificação mestre, docs/roadmap.md e ADRs; inspecione os módulos afetados. Proponha a menor sequência de mudanças e implemente a próxima slice da fase atual ponta a ponta. Preserve contratos e dados existentes. Valide com testes reais, verifique autorização e CPU compatibility, registre limitações e atualize a documentação. Não introduza dependências ou refactors fora do escopo sem justificativa e aprovação.

### 15.1 Formato obrigatório de relatório por entrega

1. Problema/requisito atendido.
2. Causa raiz (quando se tratar de correção).
3. Solução e decisões técnicas.
4. Arquivos criados/alterados.
5. Migrations e impacto no banco.
6. Comandos/testes executados e resultados reais.
7. Segurança e autorização validadas.
8. Impacto em CPU/dependências, imagens e digests.
9. Riscos, pendências e rollback (quando aplicável).
10. Próxima entrega incremental.

---

## 16. Restrições gerais para o Codex

- **Não criar clone literal** do Plane ou Zammad; apenas inspiração de UX e equivalência funcional.
- **Não utilizar** suas APIs ou bancos em produção: o Altvia Workspace é independente.
- **Não introduzir Elasticsearch/OpenSearch/MongoDB** ou componente que exija AVX/SSE4.2 no MVP sem ADR e autorização explícita.
- **Não executar código arbitrário** a partir das regras de automação.
- **Não expor dados de diferentes clientes** via filtros, links, anexos ou busca.
- **Não usar dados fictícios como se fossem dados reais** em dashboards.
- **Não duplicar ticket e tarefa** como efeito colateral inevitável de uma atribuição.
- **Não assumir que todos os tickets são tarefas de projeto.**
- **Não usar secrets hardcoded.**
- **Não executar alterações destrutivas** de banco, credenciais ou produção sem avaliar impacto, reversibilidade e aprovação.
- **Não remover recursos existentes nem fazer refactors amplos** sem necessidade técnica.
- **Não marcar feature completa sem testar** APIs, persistência, UI, permissões e fluxos de erro.
- **Não prometer compatibilidade de CPU apenas em teoria:** testar os binários reais na VM.

---

## 17. Questões a resolver na Fase 0, sem paralisar todo o trabalho

1. Hypervisor é gerenciado internamente ou por provedor? Existe possibilidade segura de mudar modelo de CPU virtual? **Até confirmação, manter x86-64-v1 como obrigatório.**
2. RAM, disco, armazenamento persistente e quantidade de tickets/e-mails diários — dimensionamento depende desses números.
3. Quais contas de e-mail serão integradas e quais políticas SMTP/IMAP se aplicam?
4. Quais são os escopos de clientes, equipes e permissões reais?
5. Qual mapeamento exato de `Frente / Cliente` para clients/projects/areas?
6. Como representar atividades `Contínua`: recorrência, registro operacional contínuo ou status customizado? Exigir ADR antes de importar.
7. Quais calendários de atendimento e políticas de SLA vigentes existem?
8. Haverá autenticação corporativa OIDC/SSO disponível?
9. Quais necessidades de retenção, proteção de dados e aprovação de mudanças exigem workflow adicional?
10. Como e quando migrar do Zammad existente (se desejado), incluindo histórico e rollback? **Não é pré-requisito do MVP inicial.**

Registrar suposições explicitamente e continuar o trabalho não destrutivo onde as respostas não forem indispensáveis. Onde houver risco de perda de dados, exposição indevida ou decisão estrutural irreversível, buscar confirmação antes de executar.

---

## 18. Estado real e entrega esperada

**Até esta versão, este arquivo é uma especificação, não um sistema implementado.** A planilha foi inspecionada para extrair a estrutura e alguns totais, mas o banco, os containers e as bibliotecas do projeto **ainda não foram testados** na VM. Não confundir requisitos ou exemplos de comandos com validações já realizadas.

**Definição de sucesso do MVP:** um funcionário entra no Altvia Workspace, consulta tickets e tarefas em My Work, recebe chamados, trabalha em projetos, atualiza progresso e registra evidências; o gestor acompanha carga, prazos, bloqueios e SLAs sem planilha; a atribuição de tickets pode gerar tarefas vinculadas de forma auditável e idempotente; o atendimento por e-mail funciona com segurança; a aplicação executa na VM-alvo x86-64-v1 sem instruções não suportadas.

**Comece pela Fase 0.**
