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

function Agents() {
  return <div>Agents</div>;
}

function Skills() {
  return <div>Skills</div>;
}

function Tools() {
  return <div>Tools</div>;
}

function Connectors() {
  return <div>Connectors</div>;
}

function MCPTools() {
  return <div>MCPTools</div>;
}
