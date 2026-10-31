import React from "react";

export default function CommonLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Auth is client-side (localStorage JWT) via AppShell — do not gate here.
  return <div className="flex min-h-0 flex-1 flex-col gap-4">{children}</div>;
}
