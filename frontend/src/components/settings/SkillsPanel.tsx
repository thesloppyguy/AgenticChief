"use client";

import { useState } from "react";
import { Brain, FileText } from "lucide-react";
import { useApi } from "@/lib/hooks";
import { Badge } from "@/components/ui/badge";
import { Loading } from "@/components/ui";
import {
  DetailPane,
  PanelEmpty,
  PanelIntro,
  PanelShell,
  SideList,
  SideListItem,
  SideListSection,
} from "@/components/settings/panel-chrome";

type SkillRow = {
  name: string;
  category: string;
  description: string;
  when_to_use: string;
  source: string;
  customized: boolean;
};

type SkillDetail = SkillRow & { body: string };

export function SkillsPanel() {
  const { data, error, loading } = useApi<SkillRow[]>("/skills");
  const [name, setName] = useState<string | null>(null);
  const detail = useApi<SkillDetail>(name ? `/skills/${name}` : null);

  const byCat = (data || []).reduce<Record<string, SkillRow[]>>((acc, s) => {
    (acc[s.category] ||= []).push(s);
    return acc;
  }, {});

  return (
    <PanelShell>
      <PanelIntro
        title="Skills"
        description="Markdown playbooks the Executive can search and load during a run."
        count={data ? `${data.length} skills` : undefined}
      />
      <Loading error={error} loading={loading && !data} />
      {data && (
        <div className="grid min-h-0 flex-1 gap-4 sm:grid-cols-[260px_1fr]">
          <SideList>
            {Object.entries(byCat)
              .sort(([a], [b]) => a.localeCompare(b))
              .map(([cat, rows]) => (
                <SideListSection key={cat} title={cat}>
                  {rows.map((s) => (
                    <SideListItem
                      key={s.name}
                      icon={FileText}
                      active={name === s.name}
                      onClick={() => setName(s.name)}
                      hint={
                        s.customized ? (
                          <span
                            className="size-1.5 shrink-0 rounded-full bg-neutral-700"
                            title="Customized"
                          />
                        ) : undefined
                      }
                    >
                      {s.name}
                    </SideListItem>
                  ))}
                </SideListSection>
              ))}
          </SideList>
          <DetailPane className="flex flex-col">
            {!name && (
              <PanelEmpty
                icon={Brain}
                title="Select a skill"
                description="Pick a playbook to read its description, when-to-use guidance, and full markdown body."
              />
            )}
            {detail.data && (
              <>
                <div className="shrink-0 space-y-2 border-b border-black/5 pb-4 dark:border-white/10">
                  <div className="text-lg font-semibold text-foreground">
                    {detail.data.name}
                  </div>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Badge variant="outline">{detail.data.source}</Badge>
                    <Badge variant="outline">{detail.data.category}</Badge>
                    {detail.data.customized && (
                      <Badge variant="outline">customized</Badge>
                    )}
                  </div>
                </div>
                <p className="shrink-0 text-pretty text-sm leading-relaxed text-foreground">
                  {detail.data.description}
                </p>
                <div className="shrink-0 rounded-2xl bg-muted/50 px-4 py-3">
                  <div className="mb-1 text-[11px] font-semibold uppercase text-muted-foreground">
                    When to use
                  </div>
                  <p className="text-pretty text-sm leading-relaxed text-foreground/80">
                    {detail.data.when_to_use}
                  </p>
                </div>
                <pre className="min-h-0 flex-1 overflow-auto whitespace-pre-wrap rounded-2xl bg-muted/40 p-4 text-xs leading-relaxed text-foreground">
                  {detail.data.body}
                </pre>
              </>
            )}
          </DetailPane>
        </div>
      )}
    </PanelShell>
  );
}
