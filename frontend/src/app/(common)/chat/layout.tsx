export default function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // ChatSessionProvider lives in AppShell so the right-rail Copilot shares state.
  return children;
}
