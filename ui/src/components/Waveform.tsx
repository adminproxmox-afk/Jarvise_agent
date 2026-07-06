import { motion } from "framer-motion";

const bars = Array.from({ length: 48 }, (_, index) => index);

export function Waveform({ active }: { active: boolean }) {
  return (
    <div className="waveform" aria-label="Voice waveform">
      {bars.map((bar) => (
        <motion.span
          key={bar}
          animate={{
            height: active ? [8, 28 + ((bar * 7) % 34), 12 + ((bar * 11) % 22)] : 8 + ((bar * 5) % 10),
            opacity: active ? [0.42, 1, 0.6] : 0.28,
          }}
          transition={{
            duration: 0.85 + (bar % 7) * 0.05,
            repeat: Infinity,
            repeatType: "mirror",
            ease: "easeInOut",
          }}
        />
      ))}
    </div>
  );
}
