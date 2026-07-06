import { motion } from "framer-motion";

export function Radar({ active }: { active: boolean }) {
  return (
    <div className="radar" aria-label="Radar scan">
      <div className="radar-grid" />
      <motion.div
        className="radar-sweep"
        animate={{ rotate: 360 }}
        transition={{ duration: active ? 2.8 : 6, repeat: Infinity, ease: "linear" }}
      />
      <div className="radar-dot dot-a" />
      <div className="radar-dot dot-b" />
      <div className="radar-dot dot-c" />
    </div>
  );
}
