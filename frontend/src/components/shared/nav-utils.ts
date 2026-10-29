export function isRouteActive(pathname: string, url: string) {
  if (!url || url === "#") return false;
  if (url === "/") return pathname === "/";
  return pathname === url || pathname.startsWith(`${url}/`);
}
