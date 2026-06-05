import type { RagSource } from "@/types/chat";

/** Normalize API `sources` payloads (handles missing or malformed arrays). */
export function normalizeSources(raw: unknown): RagSource[] {
  if (!Array.isArray(raw)) {
    return [];
  }

  return raw
    .map((item): RagSource | null => {
      if (!item || typeof item !== "object") {
        return null;
      }
      const record = item as Record<string, unknown>;
      const filename = String(record.filename ?? "").trim();
      const snippet = String(record.snippet ?? "").trim();
      if (!filename && !snippet) {
        return null;
      }
      return {
        filename: filename || "unknown_source.md",
        friendly_name: record.friendly_name
          ? String(record.friendly_name).trim()
          : undefined,
        snippet,
      };
    })
    .filter((item): item is RagSource => item !== null);
}
