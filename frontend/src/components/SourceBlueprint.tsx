"use client";

import { motion, AnimatePresence } from "framer-motion";
import { BookOpen } from "lucide-react";
import type { RagSource } from "@/types/chat";

type SourceBlueprintProps = {
  sources: RagSource[];
};

export function SourceBlueprint({ sources }: SourceBlueprintProps) {
  return (
    <div className="mt-6 pt-6 border-t border-white/10">
      <div className="flex items-center gap-2 mb-4">
        <div className="p-1.5 bg-cyan-500/20 rounded-lg border border-cyan-500/30">
          <BookOpen className="w-4 h-4 text-cyan-400" />
        </div>
        <h3 className="text-sm font-semibold text-white">Source Blueprint</h3>
      </div>

      <AnimatePresence initial={false}>
        {sources.length === 0 ? (
          <motion.p
            key="empty"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.3 }}
            className="text-xs text-gray-500 italic text-center py-4"
          >
            Ask a physics question to see which Feynman texts inform the reply.
          </motion.p>
        ) : (
          <motion.ul
            key={`sources-${sources.map((s) => s.filename).join("|")}`}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.45, ease: "easeOut" }}
            className="space-y-3"
          >
            {sources.map((source, index) => (
              <motion.li
                key={`${source.filename}-${index}`}
                initial={{ opacity: 0, x: -16 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: index * 0.08, duration: 0.35 }}
                className="p-3 rounded-xl bg-white/5 border border-white/10 shadow-inner"
              >
                <p className="text-sm font-bold text-cyan-200/90 truncate" title={source.filename}>
                  {source.filename}
                </p>
                <p className="mt-2 text-xs text-gray-400 leading-relaxed line-clamp-4">
                  {source.snippet}
                </p>
              </motion.li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </div>
  );
}
