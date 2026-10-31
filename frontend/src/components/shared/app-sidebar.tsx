"use client";

import * as React from "react";
import Link from "next/link";
import {
  Home,
  ListChecks,
  SquareTerminal,
  FileText,
  Workflow,
  Building,
  Brain,
  Box,
  Cloud,
  FileBarChart,
} from "lucide-react";

import { NavConversations } from "@/components/shared/nav-conversations";
import { NavMain } from "@/components/shared/nav-main";
import { NavLists } from "@/components/shared/nav-project";
import { NavUser } from "@/components/shared/nav-user";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";
import Logo from "@/components/Logo";

const data = {
  user: {
    name: "Lokibots",
    email: "admin@lokibots.com",
    avatar: "/avatars/shadcn.jpg",
  },
  navMain: [
    {
      title: "Home",
      url: "/home",
      icon: Home,
    },
    {
      title: "Chat",
      url: "/chat",
      icon: SquareTerminal,
    },
    {
      title: "Company",
      url: "/company",
      icon: Building,
    },
    {
      title: "Work",
      url: "#",
      icon: ListChecks,
      items: [
        {
          title: "Actions",
          url: "/actions",
          icon: ListChecks,
        },
        {
          title: "Workflows",
          url: "/workflows",
          icon: Workflow,
        },
        {
          title: "Reports",
          url: "/reports",
          icon: FileBarChart,
        },
      ],
    },
    {
      title: "Knowledge",
      url: "#",
      icon: Brain,
      items: [
        {
          title: "Documents",
          url: "/documents",
          icon: FileText,
        },
        {
          title: "Memory Store",
          url: "/memory",
          icon: Box,
        },
        {
          title: "Scorecard",
          url: "/knowledge",
          icon: Brain,
        },
      ],
    },
    {
      title: "Dream",
      url: "/dream",
      icon: Cloud,
    },
  ],
};

export function AppSidebar({
  open,
  onOpenChange,
  ...props
}: React.ComponentProps<typeof Sidebar> & {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Sidebar variant="inset" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" render={<Link href="/home" prefetch />}>
              <div className="flex aspect-square size-8 items-center justify-center rounded-full bg-accent text-accent-foreground">
                <Logo label={false} className="p-1" />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate text-base font-semibold">Lokibots</span>
                <span className="truncate text-xs text-muted-foreground">CHRO Copilot</span>
              </div>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        <NavLists title="Reports & Analytics" lists="reports" />
        <NavConversations />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={data.user} open={open} onOpenChange={onOpenChange} />
      </SidebarFooter>
    </Sidebar>
  );
}
