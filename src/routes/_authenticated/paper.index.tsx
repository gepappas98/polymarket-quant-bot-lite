import { createFileRoute } from "@tanstack/react-router";
import { PaperDesk } from "@/components/paper/PaperDesk";

export const Route = createFileRoute("/_authenticated/paper/")({
  component: () => <PaperDesk />,
});
