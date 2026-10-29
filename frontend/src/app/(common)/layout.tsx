import React from "react";

export default function CommonLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Auth is client-side (localStorage JWT) via AppShell — do not gate here.
  return <>{children}</>;
}
