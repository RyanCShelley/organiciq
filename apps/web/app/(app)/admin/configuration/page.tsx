import { redirect } from "next/navigation";

export default function AdminConfigurationRedirect() {
  redirect("/platform/settings");
}
