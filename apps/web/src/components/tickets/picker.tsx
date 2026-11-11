"use client";

import { useQuery } from "@tanstack/react-query";
import { RecordPicker, type Choice } from "@/components/project-workspace/picker";
import { usePaging } from "@/components/team-admin/common";

type ChoicePage = { items: Choice[]; next_cursor: string | null };
export function TicketPicker({ id, label, scope, load, value, onChange, disabled, empty }: {
  id: string; label: string; scope: string; value: Choice | null;
  load: (cursor: string | null, signal: AbortSignal) => Promise<ChoicePage>;
  onChange: (choice: Choice | null) => void; disabled: boolean; empty?: string;
}) {
  const paging = usePaging();
  const query = useQuery({ queryKey: ["ticket-reference", scope, paging.cursor], queryFn: ({ signal }) => load(paging.cursor, signal) });
  return <RecordPicker id={id} label={label} value={value} onChange={onChange}
    choices={query.data?.items ?? []} paging={paging} next={query.data?.next_cursor}
    pending={query.isPending} failed={query.isError} retry={() => void query.refetch()}
    disabled={disabled || query.isFetching || query.isError} empty={empty} />;
}
