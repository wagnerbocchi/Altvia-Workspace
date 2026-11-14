---
version: 1
slug: "unified-work"
primary_target: "apps/web/src/components/work-items/unified.tsx"
related_targets: ["apps/web/src/components/work-items/discovery.tsx", "apps/web/src/lib/unified-work.ts"]
---

# Personal unified queue

Mode: Operate. Local extension of the existing Twenty-inspired My Work surface.
ADR0040 owns eligibility, full-set consolidation and privacy. This brief does not
grant capabilities, replace the shared design system or mark acceptance complete.

THESIS: Show the employee's authorized tasks and assigned tickets once, while
keeping each domain's state and actual destination clear.
OWN-WORLD: Inherit root DESIGN.md, the offwhite sidebar, continuous neutral
working field, hairlines, system type, restrained blue and native controls.
STORY: Open the unified queue, deliberately apply search/domain/status/priority
filters, page actual results and open the task or ticket. Switch to Somente
tarefas for the incumbent advanced type/deadline filters. Separate keyed views
discard old local filters and paging; the private session owns every query.
FIRST VIEWPORT: Existing heading and short introduction lead to the labeled
Fila unificada/Somente tarefas group. Search and native filters precede aligned
title/scope, state/priority and deadline-or-queue columns. A task's visible ticket
origins sit under its title, capped at three with a real task-detail destination
for further links. Ticket numbers retain their native exact decimal strings.
STATES: Loading, submitted empty result, read error/retry and refresh hide denied
or failed cached content. Session replacement must discard even a delayed old
response. Completed tasks may retain new tickets; tickets have no invented task
deadline. Page size is never presented as a total.
FORM: Code-led extension; no new assets, global tokens, decorative cards or motion.
390/1440 light/dark, keyboard, long literal content, disclosure alignment,
overflow and axe share the same render batch. No raster ships in the product.
FINISH: Review the actual rendered result and complete the independent source/
visual acceptance before declaring the increment finished.
