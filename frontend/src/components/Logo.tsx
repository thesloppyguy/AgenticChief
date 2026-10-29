import { cn } from "@/lib/utils";
function Logo({ label, className }: { label: boolean; className: string }) {
  if (!label)
    return (
      <img
        src="https://cdn.prod.website-files.com/5f83f66bf4e71b5523030f96/601a469a2da74a06a22d3a07_32x32.png"
        alt="Logo"
        className={cn("w-32 m-auto", className)}
      />
    );
  return (
    <img
      src="https://cdn.prod.website-files.com/5f83f66bf4e71b5523030f96/5f84048116bd79b3edc1e74f_Logo.svg"
      alt="Logo"
      className={cn("w-32 m-auto", className)}
    />
  );
}

export default Logo;
