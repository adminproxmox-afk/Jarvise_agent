import { motion } from "framer-motion";
import { Disc3, Pause, Play, RotateCcw, Square, Volume2 } from "lucide-react";

import type { JarvisStatus } from "../lib/types";

type Props = {
  music?: JarvisStatus["music"];
  busy: boolean;
  onPlay: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
};

function cleanTitle(title?: string | null) {
  if (!title) return "LOCAL LIBRARY";
  return title.replace(/\s+/g, " ").replace(/\(mp3\.pm\)/i, "").trim();
}

export function MusicPanel({ music, busy, onPlay, onPause, onResume, onStop }: Props) {
  const mode = music?.mode ?? "stopped";
  const isPlaying = mode === "playing";
  const isPaused = mode === "paused";

  return (
    <motion.section
      className={`panel music-panel ${isPlaying ? "playing" : ""}`}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: "easeOut" }}
    >
      <div className="music-orbital" aria-hidden="true">
        <Disc3 size={30} />
      </div>
      <div className="music-meta">
        <span>AUDIO NODE</span>
        <strong title={cleanTitle(music?.title)}>{cleanTitle(music?.title)}</strong>
        <small>{mode.toUpperCase()} / {music?.engine?.toUpperCase() ?? "MCI"} / VOL {music?.volume ?? 0}</small>
      </div>
      <div className="music-spectrum" aria-hidden="true">
        {Array.from({ length: 22 }, (_, index) => (
          <i key={index} style={{ animationDelay: `${index * 44}ms` }} />
        ))}
      </div>
      <div className="music-controls">
        <button disabled={busy || isPlaying} onClick={onPlay} title="Play">
          <Play size={17} />
        </button>
        <button disabled={busy || !isPlaying} onClick={onPause} title="Pause">
          <Pause size={17} />
        </button>
        <button disabled={busy || !isPaused} onClick={onResume} title="Resume">
          <RotateCcw size={17} />
        </button>
        <button className="danger" disabled={busy || mode === "stopped"} onClick={onStop} title="Stop">
          <Square size={15} />
        </button>
      </div>
      <div className="volume-readout">
        <Volume2 size={15} />
        <span>{music?.volume ?? 0}%</span>
      </div>
    </motion.section>
  );
}
