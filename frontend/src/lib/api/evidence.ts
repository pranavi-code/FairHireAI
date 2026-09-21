import type { EvidenceNode, ReportResponse } from "@/lib/api/types";

export interface EvidenceBundle {
  primary: EvidenceNode;
  question: EvidenceNode | null;
  transcript: EvidenceNode | null;
  prediction: EvidenceNode | null;
}

export function normalizedEvidenceKind(node: EvidenceNode): string {
  return node.kind.replace(/[_\s-]/g, "").toLowerCase();
}

export function resolveEvidenceBundles(
  data: ReportResponse | undefined,
  requestedIds: string[],
): EvidenceBundle[] {
  const nodes = data?.evidence_nodes ?? [];
  const byId = new Map(nodes.map((node) => [node.id, node]));
  return [...new Set(requestedIds)]
    .map((id): EvidenceBundle | null => {
      const primary = byId.get(id);
      if (!primary) return null;
      const suffix =
        normalizedEvidenceKind(primary) === "evidenceclaim" ? id.split(":").at(-1) : null;
      return {
        primary,
        question: suffix ? (byId.get(`question:${suffix}`) ?? null) : null,
        transcript: suffix ? (byId.get(`transcript:${suffix}`) ?? null) : null,
        prediction: suffix ? (byId.get(`prediction:${suffix}`) ?? null) : null,
      };
    })
    .filter((item): item is EvidenceBundle => item !== null);
}
