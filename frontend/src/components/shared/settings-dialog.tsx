"use client";

import { useState } from "react";
import {
  Bot,
  Box,
  Brain,
  Building2,
  PanelLeftClose,
  PanelLeftOpen,
  Terminal,
  Wrench,
} from "lucide-react";

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
import { Button } from "@/components/ui/button";
import { AgentsPanel } from "@/components/settings/AgentsPanel";
import { SkillsPanel } from "@/components/settings/SkillsPanel";
import { ToolsPanel } from "@/components/settings/ToolsPanel";
import { ConnectorsPanel } from "@/components/settings/ConnectorsPanel";
import { CompanyProfilePanel } from "@/components/settings/CompanyProfilePanel";
import { cn } from "@/lib/utils";

const nav = [
  { name: "Company", icon: Building2 },
  { name: "Agents", icon: Bot },
  { name: "Skills", icon: Brain },
  { name: "Tools", icon: Wrench },
  { name: "Connectors", icon: Box },
  { name: "MCP Tools", icon: Terminal },
] as const;

type Tab = (typeof nav)[number]["name"];

export function SettingsDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [activeTab, setActiveTab] = useState<Tab>("Company");
  const [sidebarOpen, setSidebarOpen] = useState(true);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="h-[820px] max-h-[820px] w-[1080px] max-w-[1080px] overflow-hidden p-0 sm:max-w-[1080px]">
        <DialogTitle className="sr-only">Settings</DialogTitle>
        <DialogDescription className="sr-only">
          Agents, skills, tools, and connectors.
        </DialogDescription>
        <SidebarProvider className="h-full min-h-0 items-stretch">
          {sidebarOpen && (
            <Sidebar collapsible="none" className="hidden h-full border-r border-black/5 bg-white md:flex dark:border-white/10 dark:bg-background">
              <SidebarContent className="h-full overflow-hidden">
                <SidebarGroup>
                  <div className="px-4 pb-3 pt-4">
                    <div className="text-sm font-semibold text-foreground">Settings</div>
                    <p className="text-pretty text-xs leading-relaxed text-muted-foreground">
                      Agents, skills, tools, connectors
                    </p>
                  </div>
                  <SidebarGroupContent className="px-2">
                    <SidebarMenu>
                      {nav.map((item) => (
                        <SidebarMenuItem key={item.name}>
                          <SidebarMenuButton
                            render={<button type="button" />}
                            isActive={item.name === activeTab}
                            onClick={() => setActiveTab(item.name)}
                            className={cn(
                              "rounded-xl",
                              item.name === activeTab &&
                                "bg-muted font-medium text-foreground shadow-none",
                            )}
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
          )}
          <main className="flex h-full min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden bg-[#F4F5F4] dark:bg-background">
            <header className="flex h-11 shrink-0 items-center gap-2 border-b border-black/5 bg-white/80 px-3 backdrop-blur-sm dark:border-white/10 dark:bg-background/80">
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                aria-label={sidebarOpen ? "Hide settings menu" : "Show settings menu"}
                onClick={() => setSidebarOpen((v) => !v)}
              >
                {sidebarOpen ? <PanelLeftClose /> : <PanelLeftOpen />}
              </Button>
              {!sidebarOpen && (
                <div className="flex min-w-0 flex-1 gap-1 overflow-x-auto pb-0.5">
                  {nav.map((item) => (
                    <Button
                      key={item.name}
                      type="button"
                      size="sm"
                      variant="ghost"
                      className={cn(
                        "shrink-0",
                        item.name === activeTab
                          ? "bg-muted font-medium text-foreground ring-1 ring-border"
                          : "text-foreground/70",
                      )}
                      onClick={() => setActiveTab(item.name)}
                    >
                      <item.icon />
                      {item.name}
                    </Button>
                  ))}
                </div>
              )}
              {sidebarOpen && (
                <div className="text-sm font-semibold text-foreground">{activeTab}</div>
              )}
            </header>
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden p-4 md:p-5">
              {activeTab === "Company" && <CompanyProfilePanel />}
              {activeTab === "Agents" && <AgentsPanel />}
              {activeTab === "Skills" && <SkillsPanel />}
              {activeTab === "Tools" && <ToolsPanel />}
              {activeTab === "Connectors" && <ConnectorsPanel />}
              {activeTab === "MCP Tools" && <ConnectorsPanel mcpOnly />}
            </div>
          </main>
        </SidebarProvider>
      </DialogContent>
    </Dialog>
  );
}
