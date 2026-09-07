import { Badge } from "@/components/ui/Badge";

export function StatusBadge({
  available,
  availableLabel = "Available",
  unavailableLabel = "Unavailable",
}: {
  available: boolean;
  availableLabel?: string;
  unavailableLabel?: string;
}) {
  return (
    <Badge variant={available ? "success" : "warning"}>
      {available ? availableLabel : unavailableLabel}
    </Badge>
  );
}
