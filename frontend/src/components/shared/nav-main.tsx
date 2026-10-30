"use client";

import { useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, type LucideIcon } from "lucide-react";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar";
import { isRouteActive } from "@/components/shared/nav-utils";

export function NavMain({
  items,
}: {
  items: {
    title: string;
    url: string;
    icon: LucideIcon;
    isActive?: boolean;
    items?: {
      title: string;
      url: string;
    }[];
  }[];
}) {
  const pathname = usePathname();

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Platform</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item) => (
          <NavMainItem key={item.title} item={item} pathname={pathname} />
        ))}
      </SidebarMenu>
    </SidebarGroup>
  );
}

function NavMainItem({
  item,
  pathname,
}: {
  item: {
    title: string;
    url: string;
    icon: LucideIcon;
    isActive?: boolean;
    items?: {
      title: string;
      url: string;
    }[];
  };
  pathname: string;
}) {
  const hasChildren = Boolean(item.items?.length);
  const childActive =
    item.items?.some((sub) => isRouteActive(pathname, sub.url)) ?? false;
  const selfActive = isRouteActive(pathname, item.url);
  // A group opens itself when the route moves into it, and the user can still toggle it. Derived
  // rather than set from an effect: the override is remembered against the route state it was made
  // in, so navigating somewhere new makes it stale and the group opens again on its own.
  const shouldOpen = Boolean(item.isActive) || childActive || selfActive;
  const [override, setOverride] = useState<{ at: boolean; open: boolean } | null>(null);
  const open = override?.at === shouldOpen ? override.open : shouldOpen;
  const setOpen = (next: boolean) => setOverride({ at: shouldOpen, open: next });

  return (
    <Collapsible
      open={hasChildren ? open : undefined}
      onOpenChange={hasChildren ? setOpen : undefined}
      render={<SidebarMenuItem />}
    >
      <SidebarMenuButton
        tooltip={item.title}
        render={
          item.url && item.url !== "#" ? (
            <Link href={item.url} prefetch />
          ) : undefined
        }
        isActive={selfActive || childActive}
      >
        <item.icon />
        <span>{item.title}</span>
      </SidebarMenuButton>
      {hasChildren ? (
        <>
          <CollapsibleTrigger
            render={<SidebarMenuAction className="aria-expanded:rotate-90" />}
          >
            <ChevronRight />
            <span className="sr-only">Toggle</span>
          </CollapsibleTrigger>
          <CollapsibleContent>
            <SidebarMenuSub>
              {item.items?.map((subItem) => (
                <SidebarMenuSubItem key={subItem.title}>
                  <SidebarMenuSubButton
                    render={<Link href={subItem.url} prefetch />}
                    isActive={isRouteActive(pathname, subItem.url)}
                  >
                    <span>{subItem.title}</span>
                  </SidebarMenuSubButton>
                </SidebarMenuSubItem>
              ))}
            </SidebarMenuSub>
          </CollapsibleContent>
        </>
      ) : null}
    </Collapsible>
  );
}
