import { redirect } from "next/navigation";

// The dashboard lives at /home, where sign-in and the sidebar both point.
export default function Index() {
  redirect("/home");
}
