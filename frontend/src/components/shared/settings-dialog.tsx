"use client";

import { Bot, Box, Brain, SquareTerminal, Terminal } from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
} from "@/components/ui/sidebar";
import { useState } from "react";

import AssetList from "@/components/assets/AssetList";
import { Loading } from "@/components/ui";
import { Badge } from "@/components/ui/badge";
import { useApi } from "@/lib/hooks";
import { cn } from "@/lib/utils";
import type { CapabilityRow, ConnectionRow } from "@/lib/types";

const data = {
  nav: [
    { name: "Agents", icon: Bot, isActive: true },
    { name: "Skills", icon: Brain },
    { name: "Tools", icon: SquareTerminal },
    { name: "Connectors", icon: Box },
    { name: "MCP Tools", icon: Terminal },
  ],
};

export function SettingsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [activeTab, setActiveTab] = useState(data.nav[0].name);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden p-0 md:max-h-[500px] md:max-w-[700px] lg:max-w-[800px]">
        <DialogTitle className="sr-only">Settings</DialogTitle>
        <DialogDescription className="sr-only">
          Customize your settings here.
        </DialogDescription>
        <SidebarProvider className="items-start">
          <Sidebar collapsible="none" className="hidden md:flex">
            <SidebarContent>
              <SidebarGroup>
                <SidebarGroupContent>
                  <SidebarMenu>
                    {data.nav.map((item) => (
                      <SidebarMenuItem key={item.name}>
                        <SidebarMenuButton
                          render={<a href="#" />}
                          isActive={item.name === activeTab}
                          onClick={() => setActiveTab(item.name)}
                        >
                          <item.icon />
                          <span>{item.name}</span>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    ))}
                  </SidebarMenu>
                </SidebarGroupContent>
              </SidebarGroup>
            </SidebarContent>
          </Sidebar>
          <main className="flex h-[480px] flex-1 flex-col overflow-hidden">
            <header className="flex h-16 shrink-0 items-center gap-2 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12"></header>
            <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-4 pt-0">
              {activeTab === "Agents" && <Agents />}
              {activeTab === "Skills" && <Skills />}
              {activeTab === "Tools" && <Tools />}
              {activeTab === "Connectors" && <Connectors />}
              {activeTab === "MCP Tools" && <MCPTools />}
            </div>
          </main>
        </SidebarProvider>
      </DialogContent>
    </Dialog>
  );
}

/** Skills and agents already have a full authoring UI; it just had no home after the rewrite. */
function Agents() {
  return <AssetList kind="agent" />;
}

function Skills() {
  return <AssetList kind="skill" />;
}

const RISK_STYLE: Record<string, string> = {
  read: "border-success/30 bg-success/10 text-success",
  internal_write: "border-warning/30 bg-warning/10 text-warning",
  external_message: "border-warning/30 bg-warning/10 text-warning",
  destructive: "border-destructive/30 bg-destructive/10 text-destructive",
};

function Tools() {
  const { data, error, loading } = useApi<CapabilityRow[]>("/capabilities");
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Capabilities discovered from connected systems. Only a published, read-only one an admin has
        allowed can be offered to the Copilot.
      </p>
      <Loading error={error} loading={loading && !data} />
      {data?.length === 0 && <p className="text-sm text-muted-foreground">Nothing discovered yet.</p>}
      <ul className="divide-y">
        {data?.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
            <div className="min-w-0">
              <div className="truncate font-medium">{c.name}</div>
              <div className="truncate text-xs text-muted-foreground">{c.key}</div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Badge variant="outline" className={cn(RISK_STYLE[c.risk])}>{c.risk.replace(/_/g, " ")}</Badge>
              <Badge variant="outline">
                {c.published_version ? `published v${c.published_version}` : "unpublished"}
              </Badge>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function ConnectionList({ only }: { only?: string }) {
  const { data, error, loading } = useApi<ConnectionRow[]>("/connections");
  const rows = only ? data?.filter((c) => c.type === only) : data;
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Credentials are referenced by environment-variable name and are never stored or shown here.
      </p>
      <Loading error={error} loading={loading && !data} />
      {rows?.length === 0 && <p className="text-sm text-muted-foreground">No connections yet.</p>}
      <ul className="divide-y">
        {rows?.map((c) => (
          <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 py-2 text-sm">
            <div className="min-w-0">
              <div className="truncate font-medium">{c.name}</div>
              <div className="truncate text-xs text-muted-foreground">
                {c.type} · {c.capability_count} capabilities
              </div>
            </div>
            <Badge variant="outline"
              className={cn(c.health_status === "healthy" && "border-success/30 bg-success/10 text-success",
                c.health_status === "unhealthy" && "border-destructive/30 bg-destructive/10 text-destructive")}>
              {c.health_status}
            </Badge>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Connectors() {
  return <ConnectionList />;
}

function MCPTools() {
  return <ConnectionList only="mcp" />;
}
