import { Activity, Cpu, Database, Gauge, HardDrive, MemoryStick, RadioTower, Thermometer, Wifi } from "lucide-react";

import type { ClapStatus, SystemStats as SystemStatsType } from "../lib/types";

type Props = {
  stats: SystemStatsType | null;
  clap?: ClapStatus;
  connected: boolean;
};

export function SystemStats({ stats, clap, connected }: Props) {
  const items = [
    { label: "CPU", value: `${stats?.cpu ?? 0}%`, icon: Cpu, tone: "cyan" },
    { label: "RAM", value: `${stats?.memory ?? 0}%`, icon: MemoryStick, tone: "green" },
    { label: "DISK", value: `${stats?.disk ?? 0}%`, icon: HardDrive, tone: "amber" },
    { label: "PROC", value: `${stats?.processes ?? 0}`, icon: Database, tone: "red" },
    { label: "GPU", value: stats?.gpu ? `${stats.gpu.utilization}%` : "N/A", icon: Gauge, tone: "cyan" },
    { label: "NET", value: `${stats?.network?.down_kbps ?? 0}k`, icon: Wifi, tone: "green" },
  ];
  const topProcesses = stats?.top_processes?.slice(0, 3) ?? [];
  const temperature = stats?.gpu?.temperature ?? (stats?.temperature ? Object.values(stats.temperature)[0] : undefined);

  return (
    <section className="panel stats-panel">
      <div className="panel-title">
        <RadioTower size={18} />
        <span>SYSTEM</span>
        <b className={connected ? "online" : "offline"}>{connected ? "ONLINE" : "OFFLINE"}</b>
      </div>
      <div className="stats-grid">
        {items.map(({ label, value, icon: Icon, tone }) => (
          <div className={`stat ${tone}`} key={label}>
            <Icon size={20} />
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="telemetry-row">
        <span><Thermometer size={15} /> TEMP</span>
        <strong>{temperature ? `${temperature}C` : "N/A"}</strong>
        <span><Activity size={15} /> LOAD</span>
        <strong>{topProcesses[0]?.name ?? "idle"}</strong>
      </div>
      <div className="process-strip">
        {topProcesses.map((proc) => (
          <span key={`${proc.name}-${proc.cpu}`}>{proc.name} {proc.cpu}%</span>
        ))}
      </div>
      <div className="clap-row">
        <span>CLAP</span>
        <strong>{clap?.running ? "ARMED" : "STANDBY"}</strong>
        <small>{clap?.available ? `NOISE ${clap.noise_floor ?? 0}` : clap?.last_error ? "AUDIO CHECK" : "CALIBRATING"}</small>
      </div>
    </section>
  );
}
