import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowDown,
  ArrowUp,
  Bell,
  Bot,
  BrainCircuit,
  CheckCircle2,
  Code2,
  Database,
  Eye,
  EyeOff,
  FolderKanban,
  MemoryStick,
  MessageSquareText,
  Play,
  Plus,
  PlugZap,
  Power,
  Radio,
  RefreshCcw,
  Send,
  Settings,
  Shield,
  SlidersHorizontal,
  Square,
  Terminal,
  Trash2,
  Wrench,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import {
  activate,
  cancelTask,
  createTask,
  executeTool,
  getAgents,
  getMemory,
  getModels,
  getNotifications,
  getTasks,
  getTelegramStatus,
  getTools,
  pauseMusic,
  playMusic,
  rememberMemory,
  resetModelSelection,
  resumeMusic,
  sendCommand,
  selectModel,
  startMode,
  stopMusic,
  testModelProvider,
  testTelegram,
} from "./lib/api";
import type {
  AgentDescriptor,
  JarvisEvent,
  MemoryItem,
  ModelsStatus,
  TaskRecord,
  TelegramStatus,
  ToolDescriptor,
} from "./lib/types";
import { useJarvisSocket } from "./lib/useJarvisSocket";
import { ConsoleFeed } from "./components/ConsoleFeed";
import { MusicPanel } from "./components/MusicPanel";
import { SystemStats } from "./components/SystemStats";

type ViewId =
  | "chat"
  | "tasks"
  | "agents"
  | "memory"
  | "models"
  | "tools"
  | "projects"
  | "notifications"
  | "settings"
  | "telegram";

const navItems = [
  { id: "chat", label: "Chat", icon: MessageSquareText },
  { id: "tasks", label: "Tasks", icon: Activity },
  { id: "agents", label: "Agents", icon: Bot },
  { id: "memory", label: "Memory", icon: MemoryStick },
  { id: "models", label: "Models", icon: BrainCircuit },
  { id: "tools", label: "Tools", icon: Wrench },
  { id: "projects", label: "Projects", icon: FolderKanban },
  { id: "notifications", label: "Notifications", icon: Bell },
  { id: "settings", label: "Settings", icon: Settings },
  { id: "telegram", label: "Telegram", icon: Radio },
] as const;

type NavItemConfig = {
  id: ViewId;
  label: string;
  visible: boolean;
  order: number;
};

type QuickActionKind = "command" | "mode" | "music" | "activate";

type QuickAction = {
  id: string;
  label: string;
  icon: QuickActionIcon;
  kind: QuickActionKind;
  value: string;
  visible: boolean;
  order: number;
  builtIn?: boolean;
};

type MenuConfig = {
  navItems: NavItemConfig[];
  quickActions: QuickAction[];
};

const quickActionIcons = {
  Code2,
  MessageSquareText,
  Play,
  Power,
  Radio,
  Shield,
  SlidersHorizontal,
  Square,
  Terminal,
  Wrench,
} satisfies Record<string, LucideIcon>;

type QuickActionIcon = keyof typeof quickActionIcons;

const menuStorageKey = "jarvis.menu.config.v1";

const defaultQuickActions: QuickAction[] = [
  { id: "coding", label: "Coding", icon: "Code2", kind: "mode", value: "coding", visible: true, order: 0, builtIn: true },
  { id: "focus", label: "Focus", icon: "Shield", kind: "mode", value: "focus", visible: true, order: 1, builtIn: true },
  { id: "music", label: "Music", icon: "Play", kind: "music", value: "play", visible: true, order: 2, builtIn: true },
  { id: "stop", label: "Stop", icon: "Square", kind: "music", value: "stop", visible: true, order: 3, builtIn: true },
];

const quickActionKinds = new Set<QuickActionKind>(["activate", "command", "mode", "music"]);

function createDefaultMenuConfig(): MenuConfig {
  return {
    navItems: navItems.map((item, order) => ({
      id: item.id,
      label: item.label,
      visible: true,
      order,
    })),
    quickActions: defaultQuickActions.map((action) => ({ ...action })),
  };
}

function readMenuConfig(): MenuConfig {
  if (typeof window === "undefined") return createDefaultMenuConfig();
  try {
    const raw = window.localStorage.getItem(menuStorageKey);
    return normalizeMenuConfig(raw ? JSON.parse(raw) : null);
  } catch {
    return createDefaultMenuConfig();
  }
}

function normalizeMenuConfig(raw: unknown): MenuConfig {
  const fallback = createDefaultMenuConfig();
  if (!raw || typeof raw !== "object") return fallback;
  const candidate = raw as Partial<MenuConfig>;
  const savedNav = Array.isArray(candidate.navItems) ? candidate.navItems : [];
  const savedQuick = Array.isArray(candidate.quickActions) ? candidate.quickActions : [];

  const navConfig = navItems
    .map((item, order) => {
      const saved = savedNav.find((entry) => entry && typeof entry === "object" && entry.id === item.id);
      return {
        id: item.id,
        label: typeof saved?.label === "string" && saved.label.trim() ? saved.label.trim().slice(0, 32) : item.label,
        visible: item.id === "settings" ? true : typeof saved?.visible === "boolean" ? saved.visible : true,
        order: typeof saved?.order === "number" ? saved.order : order,
      };
    })
    .sort(sortByOrder);

  const defaultIds = new Set(defaultQuickActions.map((action) => action.id));
  const mergedDefaults = defaultQuickActions.map((action) => {
    const saved = savedQuick.find((entry) => entry && typeof entry === "object" && entry.id === action.id);
    return sanitizeQuickAction({ ...action, ...(saved as Partial<QuickAction> | undefined), builtIn: true }, action);
  });
  const customActions = savedQuick
    .filter((entry) => entry && typeof entry === "object" && typeof entry.id === "string" && !defaultIds.has(entry.id))
    .map((entry, index) =>
      sanitizeQuickAction(entry as Partial<QuickAction>, {
        id: `custom-${index}`,
        label: "Command",
        icon: "MessageSquareText",
        kind: "command",
        value: "",
        visible: true,
        order: defaultQuickActions.length + index,
      }),
    )
    .filter((action) => action.label.trim());

  return {
    navItems: navConfig,
    quickActions: [...mergedDefaults, ...customActions].sort(sortByOrder),
  };
}

function sanitizeQuickAction(raw: Partial<QuickAction>, fallback: QuickAction): QuickAction {
  const icon = typeof raw.icon === "string" && raw.icon in quickActionIcons ? raw.icon : fallback.icon;
  const kind = typeof raw.kind === "string" && quickActionKinds.has(raw.kind as QuickActionKind) ? raw.kind : fallback.kind;
  return {
    id: typeof raw.id === "string" && raw.id.trim() ? raw.id.trim().slice(0, 80) : fallback.id,
    label: typeof raw.label === "string" && raw.label.trim() ? raw.label.trim().slice(0, 32) : fallback.label,
    icon: icon as QuickActionIcon,
    kind: kind as QuickActionKind,
    value: typeof raw.value === "string" ? raw.value.slice(0, 500) : fallback.value,
    visible: typeof raw.visible === "boolean" ? raw.visible : fallback.visible,
    order: typeof raw.order === "number" ? raw.order : fallback.order,
    builtIn: Boolean(raw.builtIn ?? fallback.builtIn),
  };
}

function sortByOrder<T extends { order: number; label?: string }>(left: T, right: T) {
  return left.order - right.order || String(left.label ?? "").localeCompare(String(right.label ?? ""));
}

function createCustomActionId() {
  return `custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function App() {
  const { connected, events, status, stats, phase } = useJarvisSocket();
  const [activeView, setActiveView] = useState<ViewId>("chat");
  const [menuConfig, setMenuConfig] = useState<MenuConfig>(() => readMenuConfig());
  const [command, setCommand] = useState("");
  const [busy, setBusy] = useState(false);
  const [tasks, setTasks] = useState<TaskRecord[]>([]);
  const [agents, setAgents] = useState<AgentDescriptor[]>([]);
  const [models, setModels] = useState<ModelsStatus | null>(null);
  const [tools, setTools] = useState<ToolDescriptor[]>([]);
  const [memory, setMemory] = useState<MemoryItem[]>([]);
  const [notifications, setNotifications] = useState<JarvisEvent[]>([]);
  const [telegram, setTelegram] = useState<TelegramStatus | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);
  const [taskRequest, setTaskRequest] = useState("");
  const [taskAgent, setTaskAgent] = useState("");
  const [memorySection, setMemorySection] = useState("knowledge");
  const [memoryKey, setMemoryKey] = useState("");
  const [memoryValue, setMemoryValue] = useState("");
  const [modelTests, setModelTests] = useState<Record<string, string>>({});
  const [modelSelectionResult, setModelSelectionResult] = useState("");
  const [telegramTest, setTelegramTest] = useState<string>("");

  useEffect(() => {
    window.localStorage.setItem(menuStorageKey, JSON.stringify(menuConfig));
  }, [menuConfig]);

  const visibleNavItems = useMemo(
    () =>
      menuConfig.navItems
        .filter((item) => item.visible)
        .map((item) => ({ ...navItems.find((navItem) => navItem.id === item.id)!, label: item.label })),
    [menuConfig.navItems],
  );
  const visibleQuickActions = useMemo(
    () => menuConfig.quickActions.filter((action) => action.visible).sort(sortByOrder),
    [menuConfig.quickActions],
  );
  const activeViewLabel = visibleNavItems.find((item) => item.id === activeView)?.label ?? navItems.find((item) => item.id === activeView)?.label;

  useEffect(() => {
    if (!visibleNavItems.some((item) => item.id === activeView)) {
      setActiveView(visibleNavItems[0]?.id ?? "settings");
    }
  }, [activeView, visibleNavItems]);

  const refreshControlData = useCallback(async () => {
    try {
      const [taskData, agentData, modelData, toolData, memoryData, notificationData, telegramData] = await Promise.all([
        getTasks(),
        getAgents(),
        getModels(),
        getTools(),
        getMemory(),
        getNotifications(),
        getTelegramStatus(),
      ]);
      setTasks(taskData.data);
      setAgents(agentData.data);
      setModels(modelData.data);
      setTools(toolData.data);
      setMemory(memoryData.data);
      setNotifications(notificationData.data);
      setTelegram(telegramData.data);
      setDataError(null);
    } catch (error) {
      setDataError(error instanceof Error ? error.message : "JARVIS API offline");
    }
  }, []);

  useEffect(() => {
    void refreshControlData();
    const timer = window.setInterval(() => void refreshControlData(), 10000);
    return () => window.clearInterval(timer);
  }, [refreshControlData]);

  useEffect(() => {
    const latest = events[0]?.type;
    if (latest?.startsWith("task.") || latest?.startsWith("telegram.")) {
      void refreshControlData();
    }
  }, [events, refreshControlData]);

  const latestPhrase = useMemo(() => {
    const latest = events.find((event) => event.type === "ai.response" || event.type === "task.completed");
    if (typeof latest?.payload.text === "string") return latest.payload.text;
    if (typeof latest?.payload.title === "string") return latest.payload.title;
    return "Система в режиме ожидания.";
  }, [events]);

  const runningTasks = useMemo(() => tasks.filter((task) => ["pending", "running"].includes(task.status)), [tasks]);
  const completedTasks = useMemo(() => tasks.filter((task) => task.status === "completed"), [tasks]);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await fn();
      await refreshControlData();
    } finally {
      setBusy(false);
    }
  };

  const executeQuickAction = async (action: QuickAction) => {
    if (action.kind === "activate") {
      await activate();
      return;
    }
    if (action.kind === "mode") {
      await startMode(action.value || "coding");
      return;
    }
    if (action.kind === "music") {
      const musicActions: Record<string, () => Promise<unknown>> = {
        pause: pauseMusic,
        play: playMusic,
        resume: resumeMusic,
        stop: stopMusic,
      };
      await (musicActions[action.value] ?? playMusic)();
      return;
    }
    await sendCommand(action.value.trim() || action.label);
  };

  const runQuickAction = (action: QuickAction) => {
    void run(() => executeQuickAction(action));
  };

  const submitCommand = (event: FormEvent) => {
    event.preventDefault();
    const text = command.trim();
    if (!text) return;
    setCommand("");
    void run(() => sendCommand(text));
  };

  const submitTask = (event: FormEvent) => {
    event.preventDefault();
    const request = taskRequest.trim();
    if (!request) return;
    setTaskRequest("");
    void run(() => createTask({ request, agent: taskAgent || undefined }));
  };

  const submitMemory = (event: FormEvent) => {
    event.preventDefault();
    if (!memoryKey.trim() || !memoryValue.trim()) return;
    const value = parseMemoryValue(memoryValue);
    const key = memoryKey.trim();
    setMemoryKey("");
    setMemoryValue("");
    void run(() => rememberMemory({ section: memorySection, key, value }));
  };

  const testModel = (provider: string) => {
    void run(async () => {
      const result = await testModelProvider(provider);
      setModelTests((current) => ({
        ...current,
        [provider]: String(result.data.status ?? (result.data.ok ? "ok" : "failed")),
      }));
    });
  };

  const chooseModel = (provider: string, model: string) => {
    void run(async () => {
      const result = await selectModel(provider, model);
      setModelSelectionResult(String(result.data.reason ?? (result.data.ok ? "selected" : "not selected")));
    });
  };

  const clearModelChoice = () => {
    void run(async () => {
      const result = await resetModelSelection();
      setModelSelectionResult(String(result.data.reason ?? "auto routing"));
    });
  };

  const runTelegramTest = () => {
    void run(async () => {
      const result = await testTelegram();
      setTelegramTest(String(result.data.reason ?? result.data.status ?? "sent"));
    });
  };

  return (
    <main className="operator-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <BrainCircuit size={26} />
          <div>
            <strong>JARVIS</strong>
            <span>Operator</span>
          </div>
        </div>
        <div className="sidebar-scroll">
          <nav className="main-nav" aria-label="JARVIS sections">
            {visibleNavItems.map(({ id, label, icon: Icon }) => (
              <button
                className={`nav-button ${activeView === id ? "active" : ""}`}
                key={id}
                onClick={() => setActiveView(id)}
                title={label}
              >
                <Icon size={18} />
                <span>{label}</span>
              </button>
            ))}
          </nav>
          <div className="sidebar-actions" aria-label="Pinned quick actions">
            <span className="sidebar-actions-title">Quick actions</span>
            {visibleQuickActions.map((action) => {
              const Icon = quickActionIcons[action.icon];
              return (
                <button className="nav-button sidebar-action" disabled={busy} key={action.id} onClick={() => runQuickAction(action)} title={action.label}>
                  <Icon size={18} />
                  <span>{action.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </aside>

      <section className="workspace">
        <header className="workspace-header">
          <div>
            <span className="eyebrow">Control Surface</span>
            <h1>{activeViewLabel ?? "JARVIS"}</h1>
          </div>
          <div className="status-cluster">
            <StatusPill tone={connected ? "good" : "bad"} label={connected ? "Online" : "Offline"} />
            <StatusPill label={phase} />
            <StatusPill label={`${runningTasks.length} running`} />
            <button className="icon-button primary-action" disabled={busy} onClick={() => void run(activate)} title="Activate">
              <Power size={18} />
            </button>
            <button className="icon-button" disabled={busy} onClick={() => void refreshControlData()} title="Refresh">
              <RefreshCcw size={18} />
            </button>
          </div>
        </header>

        {dataError ? <div className="banner error">{dataError}</div> : null}

        {activeView === "chat" ? (
          <ChatView
            busy={busy}
            command={command}
            events={events}
            latestPhrase={latestPhrase}
            runningTasks={runningTasks}
            setCommand={setCommand}
            submitCommand={submitCommand}
            quickActions={visibleQuickActions}
            onQuickAction={runQuickAction}
          />
        ) : null}

        {activeView === "tasks" ? (
          <TasksView
            agents={agents}
            busy={busy}
            taskAgent={taskAgent}
            taskRequest={taskRequest}
            tasks={tasks}
            setTaskAgent={setTaskAgent}
            setTaskRequest={setTaskRequest}
            submitTask={submitTask}
            onCancel={(taskId) => run(() => cancelTask(taskId))}
          />
        ) : null}

        {activeView === "agents" ? <AgentsView agents={agents} tasks={tasks} /> : null}
        {activeView === "memory" ? (
          <MemoryView
            memory={memory}
            memoryKey={memoryKey}
            memorySection={memorySection}
            memoryValue={memoryValue}
            setMemoryKey={setMemoryKey}
            setMemorySection={setMemorySection}
            setMemoryValue={setMemoryValue}
            submitMemory={submitMemory}
          />
        ) : null}
        {activeView === "models" ? (
          <ModelsView
            busy={busy}
            modelSelectionResult={modelSelectionResult}
            modelTests={modelTests}
            models={models}
            onResetSelection={clearModelChoice}
            onSelect={chooseModel}
            onTest={testModel}
          />
        ) : null}
        {activeView === "tools" ? <ToolsView tools={tools} /> : null}
        {activeView === "projects" ? <ProjectsView completedTasks={completedTasks} memory={memory} tasks={tasks} /> : null}
        {activeView === "notifications" ? <ConsoleFeed events={notifications.length ? notifications : events} /> : null}
        {activeView === "settings" ? (
          <SettingsView
            status={status}
            tools={tools}
            models={models}
            menuConfig={menuConfig}
            onMenuConfigChange={setMenuConfig}
            onMenuReset={() => setMenuConfig(createDefaultMenuConfig())}
          />
        ) : null}
        {activeView === "telegram" ? (
          <TelegramView busy={busy} result={telegramTest} status={telegram} onTest={runTelegramTest} />
        ) : null}
      </section>

      <aside className="right-rail">
        <SystemStats connected={connected} stats={stats} clap={status?.clap} />
        <MusicPanel
          busy={busy}
          music={status?.music}
          onPlay={() => void run(playMusic)}
          onPause={() => void run(pauseMusic)}
          onResume={() => void run(resumeMusic)}
          onStop={() => void run(stopMusic)}
        />
      </aside>
    </main>
  );
}

function ChatView({
  busy,
  command,
  events,
  latestPhrase,
  onQuickAction,
  quickActions,
  runningTasks,
  setCommand,
  submitCommand,
}: {
  busy: boolean;
  command: string;
  events: JarvisEvent[];
  latestPhrase: string;
  onQuickAction: (action: QuickAction) => void;
  quickActions: QuickAction[];
  runningTasks: TaskRecord[];
  setCommand: (value: string) => void;
  submitCommand: (event: FormEvent) => void;
}) {
  const transcript = events.filter((event) => event.type === "ai.response" || event.type.startsWith("task.")).slice(0, 8);
  return (
    <div className="view-grid chat-grid">
      <section className="surface command-surface">
        <div className="section-title">
          <MessageSquareText size={18} />
          <span>Dialog</span>
        </div>
        <div className="assistant-response">{latestPhrase}</div>
        <form className="composer" onSubmit={submitCommand}>
          <input value={command} onChange={(event) => setCommand(event.target.value)} placeholder="Команда JARVIS" />
          <button disabled={busy || !command.trim()} type="submit" title="Send">
            <Send size={18} />
          </button>
        </form>
        <div className="quick-row">
          {quickActions.map((action) => {
            const Icon = quickActionIcons[action.icon];
            return (
              <button disabled={busy} key={action.id} onClick={() => onQuickAction(action)} title={action.label}>
                <Icon size={17} />
                <span>{action.label}</span>
              </button>
            );
          })}
        </div>
      </section>

      <section className="surface">
        <div className="section-title">
          <Activity size={18} />
          <span>Running</span>
        </div>
        <TaskStack tasks={runningTasks.slice(0, 4)} compact />
      </section>

      <section className="surface wide">
        <div className="section-title">
          <Terminal size={18} />
          <span>Recent Events</span>
        </div>
        <EventList events={transcript} />
      </section>
    </div>
  );
}

function TasksView({
  agents,
  busy,
  taskAgent,
  taskRequest,
  tasks,
  setTaskAgent,
  setTaskRequest,
  submitTask,
  onCancel,
}: {
  agents: AgentDescriptor[];
  busy: boolean;
  taskAgent: string;
  taskRequest: string;
  tasks: TaskRecord[];
  setTaskAgent: (value: string) => void;
  setTaskRequest: (value: string) => void;
  submitTask: (event: FormEvent) => void;
  onCancel: (taskId: number) => Promise<void>;
}) {
  return (
    <div className="view-grid tasks-grid">
      <form className="surface task-form" onSubmit={submitTask}>
        <div className="section-title">
          <Activity size={18} />
          <span>New Task</span>
        </div>
        <textarea value={taskRequest} onChange={(event) => setTaskRequest(event.target.value)} placeholder="Создай CRM на FastAPI и React" />
        <div className="form-row">
          <select value={taskAgent} onChange={(event) => setTaskAgent(event.target.value)}>
            <option value="">Auto agent</option>
            {agents.map((agent) => (
              <option key={agent.name} value={agent.name}>{agent.title}</option>
            ))}
          </select>
          <button disabled={busy || !taskRequest.trim()} type="submit">
            <Play size={17} />
            <span>Start</span>
          </button>
        </div>
      </form>
      <section className="surface task-list-surface">
        <div className="section-title">
          <CheckCircle2 size={18} />
          <span>Queue</span>
        </div>
        <TaskStack tasks={tasks} onCancel={onCancel} />
      </section>
    </div>
  );
}

function AgentsView({ agents, tasks }: { agents: AgentDescriptor[]; tasks: TaskRecord[] }) {
  return (
    <div className="card-grid">
      {agents.map((agent) => {
        const count = tasks.filter((task) => task.agent === agent.name).length;
        return (
          <section className="surface agent-card" key={agent.name}>
            <div className="section-title">
              <Bot size={18} />
              <span>{agent.title}</span>
              <b>{count}</b>
            </div>
            <p>{agent.role}</p>
            <TagRow items={agent.capabilities} />
            <div className="tool-strip">{agent.tools.map((tool) => <span key={tool}>{tool}</span>)}</div>
          </section>
        );
      })}
    </div>
  );
}

function MemoryView({
  memory,
  memoryKey,
  memorySection,
  memoryValue,
  setMemoryKey,
  setMemorySection,
  setMemoryValue,
  submitMemory,
}: {
  memory: MemoryItem[];
  memoryKey: string;
  memorySection: string;
  memoryValue: string;
  setMemoryKey: (value: string) => void;
  setMemorySection: (value: string) => void;
  setMemoryValue: (value: string) => void;
  submitMemory: (event: FormEvent) => void;
}) {
  return (
    <div className="view-grid memory-grid">
      <form className="surface memory-form" onSubmit={submitMemory}>
        <div className="section-title">
          <Database size={18} />
          <span>Store</span>
        </div>
        <select value={memorySection} onChange={(event) => setMemorySection(event.target.value)}>
          <option value="user_profile">User Profile</option>
          <option value="projects">Projects</option>
          <option value="context">Context</option>
          <option value="knowledge">Knowledge</option>
        </select>
        <input value={memoryKey} onChange={(event) => setMemoryKey(event.target.value)} placeholder="key" />
        <textarea value={memoryValue} onChange={(event) => setMemoryValue(event.target.value)} placeholder="value" />
        <button disabled={!memoryKey.trim() || !memoryValue.trim()} type="submit">
          <CheckCircle2 size={17} />
          <span>Save</span>
        </button>
      </form>
      <section className="surface memory-list">
        <div className="section-title">
          <MemoryStick size={18} />
          <span>Records</span>
        </div>
        <div className="record-list">
          {memory.map((item) => (
            <article className="record-row" key={item.id}>
              <b>{item.section}</b>
              <strong>{item.key}</strong>
              <span>{formatValue(item.value)}</span>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function ModelsView({
  busy,
  modelSelectionResult,
  modelTests,
  models,
  onResetSelection,
  onSelect,
  onTest,
}: {
  busy: boolean;
  modelSelectionResult: string;
  modelTests: Record<string, string>;
  models: ModelsStatus | null;
  onResetSelection: () => void;
  onSelect: (provider: string, model: string) => void;
  onTest: (provider: string) => void;
}) {
  const routing = Object.entries(models?.routing ?? {});
  const selectionLabel = models?.selection ? `${models.selection.provider} / ${models.selection.model}` : "Auto routing";
  return (
    <div className="view-grid models-grid">
      <section className="surface">
        <div className="section-title">
          <PlugZap size={18} />
          <span>Routing</span>
          <button className="section-icon-action" disabled={busy || !models?.selection} onClick={onResetSelection} title="Auto routing" type="button">
            <RefreshCcw size={15} />
          </button>
        </div>
        <Metric label="Active" value={selectionLabel} />
        <Metric label="Mode" value={models?.free_only ? "Free only" : "All models"} />
        <div className="route-list">
          {routing.map(([task, provider]) => (
            <div className="route-row" key={task}>
              <span>{task}</span>
              <b>{provider}</b>
            </div>
          ))}
        </div>
        {modelSelectionResult ? <div className="banner">{modelSelectionResult}</div> : null}
      </section>
      <section className="surface provider-list">
        <div className="section-title">
          <BrainCircuit size={18} />
          <span>Providers</span>
        </div>
        {models?.providers.map((provider) => {
          const activeModel = provider.selected && models.selection ? models.selection.model : provider.model;
          const fallbackOption = {
            id: activeModel,
            display_name: activeModel,
            provider: provider.name,
            source: "configured",
            free: provider.free,
            supports_chat: true,
          };
          const baseOptions = provider.available_models.length ? provider.available_models : [fallbackOption];
          const options = baseOptions.some((option) => option.id === activeModel) ? baseOptions : [fallbackOption, ...baseOptions];
          return (
            <article className="provider-row" key={provider.name}>
              <div>
                <strong>{provider.display_name}</strong>
                <select value={activeModel} onChange={(event) => onSelect(provider.name, event.target.value)} disabled={busy}>
                  {options.map((option) => (
                    <option key={option.id} value={option.id}>
                      {option.display_name || option.id}
                    </option>
                  ))}
                </select>
              </div>
              <StatusPill tone={provider.configured ? "good" : "warn"} label={provider.configured ? "configured" : "missing"} />
              <TagRow items={[provider.cost, provider.free ? "free" : "blocked", ...provider.routed_tasks]} />
              <button disabled={busy} onClick={() => onTest(provider.name)} title="Test connection">
                <RefreshCcw size={16} />
                <span>{modelTests[provider.name] ?? "Test"}</span>
              </button>
            </article>
          );
        })}
      </section>
    </div>
  );
}

function ToolsView({ tools }: { tools: ToolDescriptor[] }) {
  const [selectedTool, setSelectedTool] = useState("");
  const [selectedAction, setSelectedAction] = useState("");
  const [payload, setPayload] = useState("{}");
  const [result, setResult] = useState("");
  const [running, setRunning] = useState(false);
  const activeTool = tools.find((tool) => tool.name === selectedTool) ?? tools[0];

  useEffect(() => {
    if (!selectedTool && tools[0]) setSelectedTool(tools[0].name);
  }, [selectedTool, tools]);

  useEffect(() => {
    if (activeTool && !activeTool.actions.includes(selectedAction)) {
      setSelectedAction(activeTool.actions[0] ?? "");
    }
  }, [activeTool, selectedAction]);

  const runTool = async (event: FormEvent) => {
    event.preventDefault();
    if (!activeTool || !selectedAction) return;
    setRunning(true);
    try {
      const parsed = payload.trim() ? JSON.parse(payload) : {};
      const response = await executeTool(activeTool.name, selectedAction, parsed);
      setResult(JSON.stringify(response.data, null, 2));
    } catch (error) {
      setResult(error instanceof Error ? error.message : "Tool failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="view-grid tools-grid">
      <form className="surface tool-runner" onSubmit={runTool}>
        <div className="section-title">
          <Terminal size={18} />
          <span>Execute</span>
        </div>
        <select value={activeTool?.name ?? ""} onChange={(event) => setSelectedTool(event.target.value)}>
          {tools.map((tool) => (
            <option key={tool.name} value={tool.name}>{tool.title}</option>
          ))}
        </select>
        <select value={selectedAction} onChange={(event) => setSelectedAction(event.target.value)}>
          {(activeTool?.actions ?? []).map((action) => (
            <option key={action} value={action}>{action}</option>
          ))}
        </select>
        <textarea value={payload} onChange={(event) => setPayload(event.target.value)} spellCheck={false} />
        <button disabled={running || !activeTool || !selectedAction} type="submit">
          <Play size={17} />
          <span>{running ? "Running" : "Run"}</span>
        </button>
        {result ? <pre className="tool-result">{result}</pre> : null}
      </form>

      <div className="card-grid">
        {tools.map((tool) => (
          <section className="surface tool-card" key={tool.name}>
            <div className="section-title">
              <Wrench size={18} />
              <span>{tool.title}</span>
              <StatusPill tone={tool.enabled ? "good" : "bad"} label={tool.enabled ? "on" : "off"} />
            </div>
            <p>{tool.description}</p>
            <TagRow items={[tool.category, tool.access, ...tool.actions]} />
          </section>
        ))}
      </div>
    </div>
  );
}

function ProjectsView({
  completedTasks,
  memory,
  tasks,
}: {
  completedTasks: TaskRecord[];
  memory: MemoryItem[];
  tasks: TaskRecord[];
}) {
  const projectMemory = memory.filter((item) => item.section === "projects");
  const codingTasks = tasks.filter((task) => task.agent === "coding");
  return (
    <div className="view-grid projects-grid">
      <section className="surface">
        <div className="section-title">
          <FolderKanban size={18} />
          <span>Active Projects</span>
        </div>
        <TaskStack tasks={codingTasks.slice(0, 6)} compact />
      </section>
      <section className="surface">
        <div className="section-title">
          <CheckCircle2 size={18} />
          <span>Completed</span>
          <b>{completedTasks.length}</b>
        </div>
        <TaskStack tasks={completedTasks.slice(0, 5)} compact />
      </section>
      <section className="surface wide">
        <div className="section-title">
          <Database size={18} />
          <span>Project Memory</span>
        </div>
        <div className="record-list">
          {projectMemory.map((item) => (
            <article className="record-row" key={item.id}>
              <b>{item.key}</b>
              <span>{formatValue(item.value)}</span>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function SettingsView({
  menuConfig,
  models,
  onMenuConfigChange,
  onMenuReset,
  status,
  tools,
}: {
  menuConfig: MenuConfig;
  models: ModelsStatus | null;
  onMenuConfigChange: (config: MenuConfig) => void;
  onMenuReset: () => void;
  status: ReturnType<typeof useJarvisSocket>["status"];
  tools: ToolDescriptor[];
}) {
  const [newActionKind, setNewActionKind] = useState<QuickActionKind>("command");
  const [newActionLabel, setNewActionLabel] = useState("");
  const [newActionValue, setNewActionValue] = useState("");

  const updateNavItem = (id: ViewId, patch: Partial<NavItemConfig>) => {
    onMenuConfigChange({
      ...menuConfig,
      navItems: menuConfig.navItems.map((item) =>
        item.id === id
          ? {
              ...item,
              ...patch,
              visible: item.id === "settings" ? true : patch.visible ?? item.visible,
            }
          : item,
      ),
    });
  };

  const updateQuickAction = (id: string, patch: Partial<QuickAction>) => {
    onMenuConfigChange({
      ...menuConfig,
      quickActions: menuConfig.quickActions.map((action) => (action.id === id ? sanitizeQuickAction({ ...action, ...patch }, action) : action)),
    });
  };

  const deleteQuickAction = (id: string) => {
    onMenuConfigChange({
      ...menuConfig,
      quickActions: menuConfig.quickActions.filter((action) => action.id !== id || action.builtIn),
    });
  };

  const moveNavItem = (id: string, direction: -1 | 1) => {
    onMenuConfigChange({ ...menuConfig, navItems: moveOrderedItem(menuConfig.navItems, id, direction) });
  };

  const moveQuickAction = (id: string, direction: -1 | 1) => {
    onMenuConfigChange({ ...menuConfig, quickActions: moveOrderedItem(menuConfig.quickActions, id, direction) });
  };

  const addQuickAction = (event: FormEvent) => {
    event.preventDefault();
    const value = resolveNewActionValue(newActionKind, newActionValue);
    if (newActionKind === "command" && !value.trim()) return;
    const label = newActionLabel.trim() || labelForNewAction(newActionKind, value);
    onMenuConfigChange({
      ...menuConfig,
      quickActions: [
        ...menuConfig.quickActions,
        {
          id: createCustomActionId(),
          label,
          icon: iconForActionKind(newActionKind),
          kind: newActionKind,
          value,
          visible: true,
          order: menuConfig.quickActions.length,
        },
      ],
    });
    setNewActionLabel("");
    setNewActionValue("");
    setNewActionKind("command");
  };

  const sortedNav = [...menuConfig.navItems].sort(sortByOrder);
  const sortedActions = [...menuConfig.quickActions].sort(sortByOrder);

  return (
    <div className="card-grid">
      <section className="surface settings-card menu-designer">
        <div className="section-title">
          <SlidersHorizontal size={18} />
          <span>Menu Builder</span>
          <button className="section-icon-action" onClick={onMenuReset} title="Reset menu" type="button">
            <RefreshCcw size={15} />
          </button>
        </div>
        <div className="menu-config-grid">
          <div className="config-column">
            <h3>Sections</h3>
            {sortedNav.map((item, index) => {
              const base = navItems.find((navItem) => navItem.id === item.id);
              const Icon = base?.icon ?? MessageSquareText;
              const ToggleIcon = item.visible ? Eye : EyeOff;
              return (
                <article className="config-row menu-row" key={item.id}>
                  <Icon size={17} />
                  <input
                    aria-label={`${base?.label ?? item.id} label`}
                    value={item.label}
                    onChange={(event) => updateNavItem(item.id, { label: event.target.value })}
                  />
                  <div className="row-actions">
                    <button disabled={index === 0} onClick={() => moveNavItem(item.id, -1)} title="Move up" type="button">
                      <ArrowUp size={15} />
                    </button>
                    <button disabled={index === sortedNav.length - 1} onClick={() => moveNavItem(item.id, 1)} title="Move down" type="button">
                      <ArrowDown size={15} />
                    </button>
                    <button
                      disabled={item.id === "settings"}
                      onClick={() => updateNavItem(item.id, { visible: !item.visible })}
                      title={item.visible ? "Hide" : "Show"}
                      type="button"
                    >
                      <ToggleIcon size={15} />
                    </button>
                  </div>
                </article>
              );
            })}
          </div>

          <div className="config-column">
            <h3>Quick Actions</h3>
            {sortedActions.map((action, index) => {
              const Icon = quickActionIcons[action.icon];
              const ToggleIcon = action.visible ? Eye : EyeOff;
              return (
                <article className="config-row action-row" key={action.id}>
                  <Icon size={17} />
                  <input value={action.label} onChange={(event) => updateQuickAction(action.id, { label: event.target.value })} aria-label="Action label" />
                  <select
                    value={action.kind}
                    onChange={(event) => {
                      const kind = event.target.value as QuickActionKind;
                      updateQuickAction(action.id, { kind, icon: iconForActionKind(kind), value: resolveNewActionValue(kind, action.value) });
                    }}
                    aria-label="Action type"
                  >
                    <option value="command">Command</option>
                    <option value="mode">Mode</option>
                    <option value="music">Music</option>
                    <option value="activate">Activate</option>
                  </select>
                  <input
                    value={action.value}
                    onChange={(event) => updateQuickAction(action.id, { value: event.target.value })}
                    placeholder={placeholderForActionKind(action.kind)}
                    disabled={action.kind === "activate"}
                    aria-label="Action value"
                  />
                  <div className="row-actions">
                    <button disabled={index === 0} onClick={() => moveQuickAction(action.id, -1)} title="Move up" type="button">
                      <ArrowUp size={15} />
                    </button>
                    <button disabled={index === sortedActions.length - 1} onClick={() => moveQuickAction(action.id, 1)} title="Move down" type="button">
                      <ArrowDown size={15} />
                    </button>
                    <button onClick={() => updateQuickAction(action.id, { visible: !action.visible })} title={action.visible ? "Hide" : "Show"} type="button">
                      <ToggleIcon size={15} />
                    </button>
                    <button disabled={action.builtIn} onClick={() => deleteQuickAction(action.id)} title="Delete custom action" type="button">
                      <Trash2 size={15} />
                    </button>
                  </div>
                </article>
              );
            })}
            <form className="add-action-form" onSubmit={addQuickAction}>
              <input value={newActionLabel} onChange={(event) => setNewActionLabel(event.target.value)} placeholder="Label" />
              <select
                value={newActionKind}
                onChange={(event) => {
                  const kind = event.target.value as QuickActionKind;
                  setNewActionKind(kind);
                  setNewActionValue(resolveNewActionValue(kind, newActionValue));
                }}
              >
                <option value="command">Command</option>
                <option value="mode">Mode</option>
                <option value="music">Music</option>
                <option value="activate">Activate</option>
              </select>
              {newActionKind === "mode" ? (
                <select value={resolveNewActionValue(newActionKind, newActionValue)} onChange={(event) => setNewActionValue(event.target.value)}>
                  <option value="coding">coding</option>
                  <option value="focus">focus</option>
                  <option value="gaming">gaming</option>
                  <option value="night">night</option>
                </select>
              ) : null}
              {newActionKind === "music" ? (
                <select value={resolveNewActionValue(newActionKind, newActionValue)} onChange={(event) => setNewActionValue(event.target.value)}>
                  <option value="play">play</option>
                  <option value="pause">pause</option>
                  <option value="resume">resume</option>
                  <option value="stop">stop</option>
                </select>
              ) : null}
              {newActionKind === "activate" ? <input value="activate" disabled /> : null}
              {newActionKind === "command" ? (
                <input value={newActionValue} onChange={(event) => setNewActionValue(event.target.value)} placeholder="відкрий chrome / open project" />
              ) : null}
              <button type="submit" title="Add quick action">
                <Plus size={16} />
                <span>Add</span>
              </button>
            </form>
          </div>
        </div>
      </section>
      <section className="surface settings-card">
        <div className="section-title">
          <Shield size={18} />
          <span>Security</span>
        </div>
        <Metric label="Access" value={status?.security?.mode ?? "developer"} />
        <Metric label="Shutdown" value="Blocked" />
        <Metric label="Roots" value={`${status?.security?.allowed_roots.length ?? 1}`} />
        <Metric label="Tools" value={`${tools.length}`} />
      </section>
      <section className="surface settings-card">
        <div className="section-title">
          <BrainCircuit size={18} />
          <span>AI</span>
        </div>
        <Metric label="Providers" value={`${models?.providers.length ?? 0}`} />
        <Metric label="Routes" value={`${Object.keys(models?.routing ?? {}).length}`} />
        <Metric label="Default" value={models?.routing.chat ?? "openai"} />
      </section>
      <section className="surface settings-card">
        <div className="section-title">
          <Radio size={18} />
          <span>Runtime</span>
        </div>
        <Metric label="Assistant" value={status?.name ?? "JARVIS"} />
        <Metric label="Clap" value={status?.clap.running ? "Armed" : "Standby"} />
        <Metric label="Music" value={status?.music?.mode ?? "stopped"} />
      </section>
    </div>
  );
}

function moveOrderedItem<T extends { id: string; order: number; label?: string }>(items: T[], id: string, direction: -1 | 1): T[] {
  const sorted = [...items].sort(sortByOrder);
  const index = sorted.findIndex((item) => item.id === id);
  const nextIndex = index + direction;
  if (index < 0 || nextIndex < 0 || nextIndex >= sorted.length) return items;
  const next = [...sorted];
  [next[index], next[nextIndex]] = [next[nextIndex], next[index]];
  return next.map((item, order) => ({ ...item, order }));
}

function iconForActionKind(kind: QuickActionKind): QuickActionIcon {
  if (kind === "activate") return "Power";
  if (kind === "mode") return "Shield";
  if (kind === "music") return "Play";
  return "MessageSquareText";
}

function resolveNewActionValue(kind: QuickActionKind, value: string): string {
  const trimmed = value.trim();
  if (kind === "activate") return "manual";
  if (kind === "mode") return trimmed || "coding";
  if (kind === "music") return ["pause", "play", "resume", "stop"].includes(trimmed) ? trimmed : "play";
  return trimmed;
}

function labelForNewAction(kind: QuickActionKind, value: string): string {
  if (kind === "activate") return "Activate";
  if (kind === "mode") return `${value || "coding"} mode`;
  if (kind === "music") return `Music ${value || "play"}`;
  return "Command";
}

function placeholderForActionKind(kind: QuickActionKind): string {
  if (kind === "mode") return "coding / focus / gaming / night";
  if (kind === "music") return "play / pause / resume / stop";
  if (kind === "activate") return "manual";
  return "Команда JARVIS";
}

function TelegramView({
  busy,
  onTest,
  result,
  status,
}: {
  busy: boolean;
  onTest: () => void;
  result: string;
  status: TelegramStatus | null;
}) {
  return (
    <div className="view-grid telegram-grid">
      <section className="surface">
        <div className="section-title">
          <Radio size={18} />
          <span>Telegram</span>
          <StatusPill tone={status?.enabled ? "good" : "warn"} label={status?.enabled ? "enabled" : "disabled"} />
        </div>
        <Metric label="Configured" value={status?.configured ? "yes" : "no"} />
        <Metric label="Chat" value={status?.chat_id || "none"} />
        <Metric label="Reports" value={`${status?.progress_report_interval_seconds ?? 300}s`} />
        <button className="action-button" disabled={busy} onClick={onTest}>
          <Send size={17} />
          <span>Test</span>
        </button>
        {result ? <div className="banner">{result}</div> : null}
      </section>
      <section className="surface">
        <div className="section-title">
          <Terminal size={18} />
          <span>Commands</span>
        </div>
        <div className="command-list">
          <code>/status</code>
          <code>/task 12</code>
          <code>создай новый проект</code>
        </div>
      </section>
    </div>
  );
}

function TaskStack({
  compact,
  onCancel,
  tasks,
}: {
  compact?: boolean;
  onCancel?: (taskId: number) => Promise<void>;
  tasks: TaskRecord[];
}) {
  if (!tasks.length) return <div className="empty-state">No records</div>;
  return (
    <div className={`task-stack ${compact ? "compact" : ""}`}>
      {tasks.map((task) => (
        <article className="task-row" key={task.id}>
          <div className="task-topline">
            <strong>#{task.id} {task.title}</strong>
            <StatusPill tone={toneForStatus(task.status)} label={task.status} />
          </div>
          <div className="progress-track">
            <span style={{ width: `${Math.max(0, Math.min(100, task.progress))}%` }} />
          </div>
          <div className="task-meta">
            <span>{task.agent}</span>
            <span>{task.model}</span>
            <span>{Math.round(task.progress)}%</span>
            {onCancel && ["pending", "running"].includes(task.status) ? (
              <button onClick={() => void onCancel(task.id)} title="Cancel">
                <XCircle size={15} />
              </button>
            ) : null}
          </div>
          {!compact ? (
            <div className="step-list">
              {task.steps.map((step, index) => (
                <span className={step.status} key={`${task.id}-${index}`}>
                  {step.status === "completed" ? "✓" : step.status === "running" ? "⟳" : "□"} {step.title}
                </span>
              ))}
            </div>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function EventList({ events }: { events: JarvisEvent[] }) {
  if (!events.length) return <div className="empty-state">No events</div>;
  return (
    <div className="event-list">
      {events.map((event) => (
        <div className="event-row" key={event.id}>
          <time>{new Date(event.timestamp).toLocaleTimeString()}</time>
          <b>{event.type}</b>
          <span>{formatValue(event.payload)}</span>
        </div>
      ))}
    </div>
  );
}

function TagRow({ items }: { items: string[] }) {
  if (!items.length) return null;
  return (
    <div className="tag-row">
      {items.map((item) => <span key={item}>{item}</span>)}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric-row">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function StatusPill({ label, tone = "neutral" }: { label: string; tone?: "neutral" | "good" | "warn" | "bad" }) {
  return <span className={`status-pill ${tone}`}>{label}</span>;
}

function parseMemoryValue(value: string) {
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function formatValue(value: unknown) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  return text.length > 140 ? `${text.slice(0, 140)}...` : text;
}

function toneForStatus(status: string): "neutral" | "good" | "warn" | "bad" {
  if (status === "completed") return "good";
  if (status === "failed" || status === "canceled") return "bad";
  if (status === "running" || status === "pending") return "warn";
  return "neutral";
}

export default App;
