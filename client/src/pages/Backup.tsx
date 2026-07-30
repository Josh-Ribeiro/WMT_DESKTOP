import { useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { StatusBadge } from "@/components/StatusBadge";
import { useAuthenticatedUser } from "@/hooks/useAuth";
import { useApi } from "@/hooks/useApi";
import { apiRequest } from "@/lib/api";
import { openPathOnHost } from "@/lib/hostOpen";
import { open as openDialog } from "@tauri-apps/plugin-dialog";
import {
  AlertTriangle,
  CheckCircle2,
  CheckSquare,
  FolderOpen,
  HardDrive,
  Loader2,
  Play,
  RefreshCw,
  RotateCcw,
  Trash2,
  Users,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { useLocation } from "wouter";

type BackupStatus =
  | "completed"
  | "running"
  | "failed"
  | "scheduled"
  | "canceled";
type BackupMode = "profiles" | "custom-folder";

interface BackupJob {
  id: string;
  workstation: string;
  source?: string;
  destination?: string;
  users?: string[];
  status: BackupStatus;
  start_time: string;
  end_time: string;
  size: string;
  progress: number;
  message?: string;
  summary?: string;
  current_step?: number;
  total_steps?: number;
  eta_seconds?: number | null;
  estimated_end_time?: string | null;
  log?: string;
  failures?: string[];
  checklist?: Record<string, boolean>;
  backup_type?: "profiles" | "custom-folder" | string;
  destination_path?: string;
  source_path?: string;
  exclude_patterns?: string[];
  validation?: {
    status?: string;
    checked_items?: number;
    failed_items?: number;
    message?: string;
  };
}

interface BackupJobsData {
  jobs: BackupJob[];
  summary: {
    total: number;
    total_size: string;
    success_rate: number;
  };
}

interface BackupUsersResponse {
  users: string[];
  count: number;
  warning?: string;
}

interface OpenDestinationResponse {
  path: string;
  message: string;
}

interface AppPreferences {
  display_language: string;
  backup_default_destination_path: string;
}

interface BackupPrecheckItem {
  name: string;
  status: "ok" | "warning" | "blocked";
  message: string;
}

interface BackupPrecheckResponse {
  status: "ok" | "warning" | "blocked";
  checks: BackupPrecheckItem[];
  warnings: string[];
  errors: string[];
  estimated_bytes: number;
  estimated_size: string;
  message: string;
}

interface BackupSimulationResponse {
  ok: boolean;
  planned_items: number;
  exclude_patterns: string[];
  message: string;
  log: string;
}

const destinationDrives = ["C:", "D:", "E:", "F:"];
const BACKUP_FOLDERS_CLIENT = [
  "Desktop",
  "Documents",
  "Downloads",
  "Favorites",
  "Pictures",
  "Videos",
];
const terminalStatuses: BackupStatus[] = ["completed", "failed", "canceled"];

function normalizeHost(value: string) {
  return value.trim().replace(/^\\\\/, "").replace(/\\/g, "").toUpperCase();
}

function remoteFolderSelectionToDrivePath(selectedPath: string, host: string) {
  const normalized = selectedPath
    .trim()
    .replace(/\//g, "\\")
    .replace(/\\+$/, "");
  const hostPrefix = `\\\\${normalizeHost(host)}\\`;
  if (!normalized.toUpperCase().startsWith(hostPrefix.toUpperCase())) {
    throw new Error(
      `Selecione uma pasta compartilhada em ${normalizeHost(host)}.`
    );
  }

  const [shareName = "", ...relativeParts] = normalized
    .slice(hostPrefix.length)
    .split("\\");
  const shareMatch = shareName.match(/^WMT_TEMP_([A-Z])\$$/i);
  if (!shareMatch) {
    throw new Error(
      "Selecione uma pasta dentro do compartilhamento temporário aberto pelo WMT."
    );
  }

  const drive = shareMatch[1].toUpperCase();
  const relative = relativeParts.filter(Boolean).join("\\");
  return relative ? `${drive}:\\${relative}` : `${drive}:\\`;
}

function formatEta(seconds?: number | null) {
  if (seconds === null || seconds === undefined || seconds <= 0) {
    return "--";
  }

  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.floor(seconds % 60);

  if (minutes <= 0) {
    return `${remainingSeconds}s`;
  }

  return `${minutes}m ${remainingSeconds.toString().padStart(2, "0")}s`;
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return "--";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "--";
  }

  return date.toLocaleString([], {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function destinationPreview(
  destination: string,
  drive: string,
  folder: string,
  enabled: boolean
) {
  if (!destination.trim()) {
    return "";
  }

  if (!enabled) {
    return `\\\\${normalizeHost(destination)}\\C$\\Users`;
  }

  const cleanFolder = folder.trim().replace(/^\\+/, "").replace(/\\+$/, "");
  const share = drive.replace(":", "$");

  return cleanFolder
    ? `\\\\${normalizeHost(destination)}\\${share}\\${cleanFolder}`
    : `\\\\${normalizeHost(destination)}\\${share}\\`;
}

function summarizedLog(log?: string) {
  const lines = (log || "")
    .split(/\r?\n/)
    .map(line => line.trimEnd())
    .filter(Boolean);

  return lines.slice(-18).join("\n");
}

export default function Backup() {
  const user = useAuthenticatedUser();
  const [, navigate] = useLocation();
  const [backupMode, setBackupMode] = useState<BackupMode>("profiles");
  const [source, setSource] = useState("");
  const [destination, setDestination] = useState("");
  const [customSourcePath, setCustomSourcePath] = useState("C:\\Temp");
  const [customDestinationPath, setCustomDestinationPath] =
    useState("D:\\Backup\\Custom");
  const [customExcludePatterns, setCustomExcludePatterns] =
    useState("*.ost;*.tmp");
  const [profileExcludePatterns, setProfileExcludePatterns] = useState("*.ost");
  const [destinationTemplates, setDestinationTemplates] = useState<string[]>(
    []
  );
  const [availableUsers, setAvailableUsers] = useState<string[]>([]);
  const [selectedUsers, setSelectedUsers] = useState<string[]>([]);
  const [usersWarning, setUsersWarning] = useState("");
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [useCustomDestination, setUseCustomDestination] = useState(true);
  const [destinationDrive, setDestinationDrive] = useState("D:");
  const [destinationFolder, setDestinationFolder] =
    useState("Backup\\Migration");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<BackupJob | null>(null);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);
  const [loadingDetailsId, setLoadingDetailsId] = useState<string | null>(null);
  const [openingDestination, setOpeningDestination] = useState(false);
  const [customBrowseLoading, setCustomBrowseLoading] = useState<
    "source" | "destination" | null
  >(null);
  const [precheckLoading, setPrecheckLoading] = useState(false);
  const [precheckResult, setPrecheckResult] =
    useState<BackupPrecheckResponse | null>(null);
  const [simulationLoading, setSimulationLoading] = useState(false);
  const [simulationResult, setSimulationResult] =
    useState<BackupSimulationResponse | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const destinationPathEditedRef = useRef(false);
  const destinationDefaultAppliedRef = useRef(false);

  const { data, loading, error, refetch } = useApi<BackupJobsData>(
    "/api/backup/jobs",
    {
      refetchInterval: 15000,
    }
  );
  const { data: appPreferences } = useApi<AppPreferences>(
    "/api/app-preferences"
  );

  const backupJobs = data?.jobs || [];
  const summary = data?.summary || {
    total: 0,
    total_size: "0 GB",
    success_rate: 0,
  };
  const destinationPath = useCustomDestination
    ? `${destinationDrive}\\${destinationFolder.trim().replace(/^\\+/, "")}`
    : "";
  const previewPath = destinationPreview(
    destination,
    destinationDrive,
    destinationFolder,
    useCustomDestination
  );
  const canLoadUsers = Boolean(source.trim());
  const canStartBackup = Boolean(
    source.trim() &&
      destination.trim() &&
      (backupMode === "custom-folder"
        ? customSourcePath.trim() && customDestinationPath.trim()
        : selectedUsers.length > 0 &&
          (!useCustomDestination || destinationFolder.trim()))
  );
  const runningJob = activeJob?.status === "running";
  const visibleActiveJob =
    activeJob || backupJobs.find(job => job.id === activeJobId) || null;

  const selectedSummary = useMemo(() => {
    if (!availableUsers.length) {
      return "No users loaded";
    }

    return `${selectedUsers.length} of ${availableUsers.length} selected`;
  }, [availableUsers.length, selectedUsers.length]);

  useEffect(() => {
    if (!activeJobId) {
      return;
    }

    let cancelled = false;

    const poll = async () => {
      if (document.hidden) {
        return;
      }
      try {
        const job = await apiRequest<BackupJob>(
          `/api/backup/jobs/${activeJobId}`
        );
        if (cancelled) {
          return;
        }

        setActiveJob(job);
        if (terminalStatuses.includes(job.status)) {
          setActiveJobId(null);
          await refetch();
        }
      } catch (err) {
        if (!cancelled) {
          toast.error(
            err instanceof Error
              ? err.message
              : "Failed to update backup progress"
          );
        }
      }
    };

    poll();
    const interval = window.setInterval(poll, 3000);
    const handleVisibility = () => {
      if (!document.hidden) {
        void poll();
      }
    };
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [activeJobId, refetch]);

  useEffect(() => {
    setPrecheckResult(null);
    setSimulationResult(null);
  }, [
    source,
    destination,
    selectedUsers,
    useCustomDestination,
    destinationDrive,
    destinationFolder,
    backupMode,
    customSourcePath,
    customDestinationPath,
    customExcludePatterns,
    profileExcludePatterns,
  ]);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(
        "wmt.backup.destinationTemplates"
      );
      const parsed = stored ? JSON.parse(stored) : [];
      setDestinationTemplates(
        Array.isArray(parsed) ? parsed.filter(Boolean) : []
      );
    } catch {
      setDestinationTemplates([]);
    }
  }, []);

  useEffect(() => {
    if (
      destinationDefaultAppliedRef.current ||
      destinationPathEditedRef.current
    ) {
      return;
    }

    const defaultPath = appPreferences?.backup_default_destination_path?.trim();
    if (!defaultPath) {
      return;
    }

    const match = defaultPath.match(/^([A-Za-z]:)[\\/]*(.*)$/);
    if (!match) {
      return;
    }

    destinationDefaultAppliedRef.current = true;
    setDestinationDrive(match[1].toUpperCase());
    setDestinationFolder(match[2].replace(/\//g, "\\"));
    setCustomDestinationPath(defaultPath.replace(/\//g, "\\"));
  }, [appPreferences]);

  const saveDestinationTemplates = (items: string[]) => {
    const unique = Array.from(
      new Set(items.map(item => item.trim()).filter(Boolean))
    ).slice(0, 12);
    setDestinationTemplates(unique);
    window.localStorage.setItem(
      "wmt.backup.destinationTemplates",
      JSON.stringify(unique)
    );
  };

  const removeDestinationTemplate = (template: string) => {
    saveDestinationTemplates(
      destinationTemplates.filter(item => item !== template)
    );
    toast.success("Pasta salva removida", { description: template });
  };

  const profileExcludeList = () =>
    profileExcludePatterns
      .split(/[;,]/)
      .map(item => item.trim())
      .filter(Boolean);

  const handleLoadUsers = async () => {
    if (!canLoadUsers) {
      toast.error("Fill source workstation first.");
      return;
    }

    setLoadingUsers(true);
    setUsersWarning("");
    try {
      const result = await apiRequest<BackupUsersResponse>(
        "/api/backup/users",
        {
          method: "POST",
          body: JSON.stringify({
            source: normalizeHost(source),
          }),
        }
      );

      setAvailableUsers(result.users);
      setSelectedUsers(result.users);
      setUsersWarning(result.warning || "");
      toast.success(`${result.count} user profiles loaded`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to load users");
    } finally {
      setLoadingUsers(false);
    }
  };

  const toggleUser = (profile: string) => {
    setSelectedUsers(current =>
      current.includes(profile)
        ? current.filter(item => item !== profile)
        : [...current, profile]
    );
  };

  const toggleAllUsers = () => {
    setSelectedUsers(current =>
      current.length === availableUsers.length ? [] : availableUsers
    );
  };

  const handleOpenDestination = async () => {
    if (!destination.trim()) {
      toast.error("Fill destination workstation first.");
      return;
    }

    setOpeningDestination(true);
    try {
      const result = await apiRequest<OpenDestinationResponse>(
        "/api/backup/open-destination",
        {
          method: "POST",
          body: JSON.stringify({
            destination: normalizeHost(destination),
            destination_path: useCustomDestination ? destinationPath : null,
          }),
        }
      );
      const selectedPath = await openDialog({
        directory: true,
        multiple: false,
        defaultPath: result.path,
        title: "Selecionar pasta de destino",
      });
      if (!selectedPath) {
        return;
      }

      const selectedDrivePath = remoteFolderSelectionToDrivePath(
        selectedPath,
        destination
      );
      const [drive = "D:", ...folderParts] = selectedDrivePath.split("\\");
      destinationPathEditedRef.current = true;
      setUseCustomDestination(true);
      setDestinationDrive(drive.endsWith(":") ? drive : "D:");
      setDestinationFolder(folderParts.join("\\"));
      toast.success("Pasta de destino selecionada", {
        description: selectedDrivePath,
      });
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to open destination"
      );
    } finally {
      setOpeningDestination(false);
    }
  };

  const handleBrowseCustomPath = async (kind: "source" | "destination") => {
    const host = kind === "source" ? source : destination;
    const path = kind === "source" ? customSourcePath : customDestinationPath;
    if (!host.trim()) {
      toast.error(
        `Informe o computador de ${kind === "source" ? "origem" : "destino"} primeiro.`
      );
      return;
    }
    if (!path.trim()) {
      toast.error(
        `Informe a pasta de ${kind === "source" ? "origem" : "destino"} primeiro.`
      );
      return;
    }

    setCustomBrowseLoading(kind);
    try {
      const result = await apiRequest<OpenDestinationResponse>(
        "/api/backup/open-destination",
        {
          method: "POST",
          body: JSON.stringify({
            destination: normalizeHost(host),
            destination_path: path.trim(),
            create_if_missing: kind === "destination",
          }),
        }
      );
      const selectedPath = await openDialog({
        directory: true,
        multiple: false,
        defaultPath: result.path,
        title:
          kind === "source"
            ? "Selecionar pasta de origem"
            : "Selecionar pasta de destino",
      });
      if (!selectedPath) {
        return;
      }

      const selectedDrivePath = remoteFolderSelectionToDrivePath(
        selectedPath,
        host
      );
      if (kind === "source") {
        setCustomSourcePath(selectedDrivePath);
      } else {
        destinationPathEditedRef.current = true;
        setCustomDestinationPath(selectedDrivePath);
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Não foi possível abrir a pasta."
      );
    } finally {
      setCustomBrowseLoading(null);
    }
  };

  const handlePrecheck = async () => {
    if (backupMode === "custom-folder") {
      toast.info(
        "Custom folder backup validates source/destination when the job starts."
      );
      return;
    }
    if (!canStartBackup) {
      toast.error("Fill backup details and select at least one user.");
      return;
    }

    setPrecheckLoading(true);
    try {
      const result = await apiRequest<BackupPrecheckResponse>(
        "/api/backup/precheck",
        {
          method: "POST",
          body: JSON.stringify({
            source: normalizeHost(source),
            destination: normalizeHost(destination),
            users: selectedUsers,
            destination_path: useCustomDestination ? destinationPath : null,
            exclude_patterns: profileExcludeList(),
          }),
        }
      );
      setPrecheckResult(result);
      if (result.status === "blocked") {
        toast.error(result.message);
      } else if (result.status === "warning") {
        toast.warning(result.message);
      } else {
        toast.success(result.message);
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to run backup pre-check"
      );
    } finally {
      setPrecheckLoading(false);
    }
  };

  const handleSimulateBackup = async () => {
    if (backupMode !== "profiles") {
      toast.info("Simulation is available for profile backups.");
      return;
    }
    if (!canStartBackup) {
      toast.error("Fill backup details and select at least one user.");
      return;
    }
    setSimulationLoading(true);
    try {
      const result = await apiRequest<BackupSimulationResponse>(
        "/api/backup/simulate",
        {
          method: "POST",
          body: JSON.stringify({
            source: normalizeHost(source),
            destination: normalizeHost(destination),
            users: selectedUsers,
            destination_path: useCustomDestination ? destinationPath : null,
            exclude_patterns: profileExcludeList(),
          }),
        }
      );
      setSimulationResult(result);
      toast.success(result.message);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to simulate backup"
      );
    } finally {
      setSimulationLoading(false);
    }
  };

  const handleStartBackup = async () => {
    if (!canStartBackup) {
      toast.error("Fill backup details and select at least one user.");
      return;
    }
    if (backupMode === "profiles" && precheckResult?.status === "blocked") {
      toast.error(
        "Pre-check has blocking issues. Fix them before starting the backup."
      );
      return;
    }

    try {
      const job =
        backupMode === "custom-folder"
          ? await apiRequest<BackupJob>("/api/backup/custom-folder/jobs", {
              method: "POST",
              body: JSON.stringify({
                source: normalizeHost(source),
                destination: normalizeHost(destination),
                source_path: customSourcePath.trim(),
                destination_path: customDestinationPath.trim(),
                exclude_patterns: customExcludePatterns
                  .split(/[;,]/)
                  .map(item => item.trim())
                  .filter(Boolean),
              }),
            })
          : await apiRequest<BackupJob>("/api/backup/jobs", {
              method: "POST",
              body: JSON.stringify({
                source: normalizeHost(source),
                destination: normalizeHost(destination),
                users: selectedUsers,
                destination_path: useCustomDestination ? destinationPath : null,
                exclude_patterns: profileExcludeList(),
              }),
            });

      setActiveJobId(job.id);
      setActiveJob(job);
      setCurrentStep(4);
      await refetch();
      toast.success("Backup started");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to start backup"
      );
    }
  };

  const handleCancelBackup = async (backupId: string) => {
    try {
      const job = await apiRequest<BackupJob>(
        `/api/backup/jobs/${backupId}/cancel`,
        {
          method: "POST",
        }
      );
      setActiveJobId(job.id);
      setActiveJob(job);
      await refetch();
      toast.success("Cancel requested");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to cancel backup"
      );
    }
  };

  const handleDeleteBackup = async (backupId: string) => {
    try {
      await apiRequest(`/api/backup/jobs/${backupId}`, { method: "DELETE" });
      if (activeJobId === backupId) {
        setActiveJobId(null);
        setActiveJob(null);
      }
      if (expandedJobId === backupId) {
        setExpandedJobId(null);
      }
      await refetch();
      toast.success("Backup removed");
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to delete backup"
      );
    }
  };

  const handleShowDetails = async (job: BackupJob) => {
    if (expandedJobId === job.id) {
      setExpandedJobId(null);
      return;
    }

    setExpandedJobId(job.id);
    setActiveJobId(job.id);
    setActiveJob(job);
    setLoadingDetailsId(job.id);
    try {
      const details = await apiRequest<BackupJob>(`/api/backup/jobs/${job.id}`);
      setActiveJob(details);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to load backup details"
      );
    } finally {
      setLoadingDetailsId(null);
    }
  };

  const handleOpenJobPath = async (
    job: BackupJob,
    kind: "source" | "destination"
  ) => {
    try {
      const result = await apiRequest<OpenDestinationResponse>(
        `/api/backup/jobs/${job.id}/open-path?kind=${kind}`
      );
      await openPathOnHost(result.path);
      toast.success(result.message || result.path);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : `Failed to open ${kind}`
      );
    }
  };

  const handleRetryFolder = async (
    job: BackupJob,
    profile: string,
    folder: string
  ) => {
    try {
      const retry = await apiRequest<BackupJob>(
        `/api/backup/jobs/${job.id}/retry-folder`,
        {
          method: "POST",
          body: JSON.stringify({ profile, folder }),
        }
      );
      setActiveJobId(retry.id);
      setActiveJob(retry);
      await refetch();
      toast.success(`Retry started for ${profile}/${folder}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to start retry");
    }
  };

  const handleRetention = async () => {
    const rawDays = window.prompt(
      "Remove backup history older than how many days?",
      "30"
    );
    if (!rawDays) return;
    const days = Number(rawDays);
    if (!Number.isFinite(days) || days <= 0) {
      toast.error("Invalid retention window.");
      return;
    }
    try {
      const result = await apiRequest<{ removed: number; kept: number }>(
        "/api/backup/jobs/retention",
        {
          method: "POST",
          body: JSON.stringify({ days, keep_last: 20 }),
        }
      );
      await refetch();
      toast.success(`Removed ${result.removed} old backup job(s).`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to clean backup history"
      );
    }
  };

  const wizardSteps = [
    { title: "Origem e destino", description: "Informe as workstations" },
    { title: "Tipo de backup", description: "Perfis ou pasta customizada" },
    {
      title: backupMode === "profiles" ? "Perfis" : "Pastas",
      description:
        backupMode === "profiles" ? "Selecione usuários" : "Confirme caminhos",
    },
    { title: "Revisão", description: "Valide e inicie" },
    { title: "Acompanhamento", description: "Progresso e histórico" },
  ];

  const canAdvanceFromStep = (step: number) => {
    if (step === 0) return Boolean(source.trim() && destination.trim());
    if (step === 1) {
      return backupMode === "custom-folder"
        ? Boolean(customSourcePath.trim() && customDestinationPath.trim())
        : Boolean(!useCustomDestination || destinationFolder.trim());
    }
    if (step === 2)
      return backupMode === "custom-folder" || selectedUsers.length > 0;
    if (step === 3) return canStartBackup;
    return true;
  };

  const goToNextStep = () =>
    setCurrentStep(step => Math.min(step + 1, wizardSteps.length - 1));
  const goToPreviousStep = () => setCurrentStep(step => Math.max(step - 1, 0));

  const stepContent = (
    <>
      {currentStep === 0 && (
        <section className="space-y-5 rounded-lg border border-border bg-card p-5 shadow-sm">
          <div>
            <h2 className="text-xl font-semibold text-foreground">
              Origem e destino
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Comece informando as duas workstations. O WMT usa sua sessão
              Windows/AD para acessar os caminhos.
            </p>
          </div>

          <div className="grid gap-4 md:grid-cols-[1fr_auto_1fr] md:items-end">
            <label className="space-y-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Workstation de origem
              </span>
              <Input
                value={source}
                onChange={event => setSource(event.target.value)}
                placeholder="WK123456"
              />
            </label>

            <Button
              className="gap-2 md:mb-0"
              variant="outline"
              onClick={handleLoadUsers}
              disabled={
                backupMode !== "profiles" || !canLoadUsers || loadingUsers
              }
            >
              {loadingUsers ? (
                <Loader2 className="animate-spin" size={16} />
              ) : (
                <Users size={16} />
              )}
              Carregar usuários
            </Button>

            <label className="space-y-2">
              <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Workstation de destino
              </span>
              <Input
                value={destination}
                onChange={event => setDestination(event.target.value)}
                placeholder="WK654321"
              />
            </label>
          </div>

          <div className="grid gap-3 rounded-lg border border-border/70 bg-muted/30 p-4 text-sm md:grid-cols-3">
            <div>
              <p className="text-muted-foreground">Origem</p>
              <p className="font-semibold text-foreground">
                {source ? normalizeHost(source) : "Não informada"}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Destino</p>
              <p className="font-semibold text-foreground">
                {destination ? normalizeHost(destination) : "Não informado"}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Perfis carregados</p>
              <p className="font-semibold text-foreground">
                {availableUsers.length}
              </p>
            </div>
          </div>
        </section>
      )}

      {currentStep === 1 && (
        <section className="space-y-5 rounded-lg border border-border bg-card p-5 shadow-sm">
          <div>
            <h2 className="text-xl font-semibold text-foreground">
              Tipo de backup
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Escolha entre migração de perfis ou cópia de uma pasta específica.
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <button
              type="button"
              className={`rounded-lg border p-4 text-left transition-colors ${backupMode === "profiles" ? "border-primary bg-primary/10" : "border-border bg-muted/20 hover:bg-muted/40"}`}
              onClick={() => setBackupMode("profiles")}
            >
              <div className="flex items-center gap-2">
                <Users size={18} className="text-primary" />
                <p className="font-semibold text-foreground">
                  Perfis de usuário
                </p>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                Copia Desktop, Documents, Downloads, Favorites, Pictures e
                Videos dos perfis selecionados.
              </p>
            </button>

            <button
              type="button"
              className={`rounded-lg border p-4 text-left transition-colors ${backupMode === "custom-folder" ? "border-primary bg-primary/10" : "border-border bg-muted/20 hover:bg-muted/40"}`}
              onClick={() => setBackupMode("custom-folder")}
            >
              <div className="flex items-center gap-2">
                <FolderOpen size={18} className="text-primary" />
                <p className="font-semibold text-foreground">
                  Pasta customizada
                </p>
              </div>
              <p className="mt-2 text-sm text-muted-foreground">
                Copia uma pasta absoluta da origem para uma pasta absoluta no
                destino.
              </p>
            </button>
          </div>

          {backupMode === "profiles" ? (
            <div className="space-y-4 rounded-lg border border-border/70 bg-muted/20 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="font-semibold text-foreground">
                    Destino dos perfis
                  </h3>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {previewPath ||
                      "Informe o destino para visualizar o caminho."}
                  </p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-sm text-muted-foreground">
                    Caminho customizado
                  </span>
                  <Switch
                    checked={useCustomDestination}
                    onCheckedChange={setUseCustomDestination}
                  />
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={handleOpenDestination}
                    disabled={openingDestination || !destination.trim()}
                  >
                    {openingDestination ? (
                      <Loader2 className="animate-spin" size={16} />
                    ) : (
                      <FolderOpen size={16} />
                    )}
                    Selecionar pasta
                  </Button>
                </div>
              </div>

              {useCustomDestination && (
                <div className="grid gap-4 md:grid-cols-[160px_1fr_auto]">
                  <label className="space-y-2">
                    <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Drive
                    </span>
                    <Select
                      value={destinationDrive}
                      onValueChange={value => {
                        destinationPathEditedRef.current = true;
                        setDestinationDrive(value);
                      }}
                    >
                      <SelectTrigger className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {destinationDrives.map(drive => (
                          <SelectItem key={drive} value={drive}>
                            {drive}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </label>
                  <label className="space-y-2">
                    <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      Pasta
                    </span>
                    <Input
                      value={destinationFolder}
                      onChange={event => {
                        destinationPathEditedRef.current = true;
                        setDestinationFolder(event.target.value);
                      }}
                      placeholder="Backup\\Migration"
                    />
                  </label>
                  <div className="flex items-end gap-2">
                    <Button
                      variant="outline"
                      onClick={() =>
                        saveDestinationTemplates([
                          destinationPath,
                          ...destinationTemplates,
                        ])
                      }
                      disabled={!destinationPath.trim()}
                    >
                      Salvar
                    </Button>
                  </div>
                </div>
              )}

              {useCustomDestination && destinationTemplates.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {destinationTemplates.map(template => (
                    <div
                      key={template}
                      className={`inline-flex h-10 max-w-full items-stretch overflow-hidden rounded-md border bg-background transition-colors focus-within:ring-2 focus-within:ring-ring/40 ${
                        destinationPath === template
                          ? "border-primary/70 bg-primary/5"
                          : "border-input"
                      }`}
                    >
                      <button
                        type="button"
                        className="flex min-w-0 items-center gap-2 px-3 text-sm font-medium text-foreground outline-none"
                        title={`Usar ${template}`}
                        onClick={() => {
                          destinationPathEditedRef.current = true;
                          const [drive = "D:", ...rest] = template.split("\\");
                          setDestinationDrive(
                            drive.endsWith(":") ? drive : "D:"
                          );
                          setDestinationFolder(rest.join("\\"));
                        }}
                      >
                        <FolderOpen
                          size={15}
                          className="shrink-0 text-primary"
                        />
                        <span className="truncate">{template}</span>
                      </button>
                      <button
                        type="button"
                        className="flex w-10 shrink-0 items-center justify-center border-l border-input text-muted-foreground outline-none transition-colors hover:bg-muted hover:text-foreground focus-visible:bg-muted focus-visible:text-foreground"
                        title={`Remover ${template}`}
                        aria-label={`Remover pasta salva ${template}`}
                        onClick={() => removeDestinationTemplate(template)}
                      >
                        <X size={17} strokeWidth={2.25} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <label className="block space-y-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Padrões excluídos
                </span>
                <Input
                  value={profileExcludePatterns}
                  onChange={event =>
                    setProfileExcludePatterns(event.target.value)
                  }
                  placeholder="*.ost;*.tmp"
                />
              </label>
            </div>
          ) : (
            <div className="space-y-4 rounded-lg border border-border/70 bg-muted/20 p-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Pasta de origem
                  </span>
                  <div className="flex gap-2">
                    <Input
                      value={customSourcePath}
                      onChange={event =>
                        setCustomSourcePath(event.target.value)
                      }
                      placeholder="C:\\Users\\username\\Desktop\\Folder"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => void handleBrowseCustomPath("source")}
                      disabled={customBrowseLoading !== null}
                    >
                      {customBrowseLoading === "source" ? (
                        <Loader2 className="animate-spin" size={16} />
                      ) : (
                        <FolderOpen size={16} />
                      )}
                      Browse
                    </Button>
                  </div>
                </div>
                <div className="space-y-2">
                  <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Pasta de destino
                  </span>
                  <div className="flex gap-2">
                    <Input
                      value={customDestinationPath}
                      onChange={event => {
                        destinationPathEditedRef.current = true;
                        setCustomDestinationPath(event.target.value);
                      }}
                      placeholder="D:\\Backup\\Custom\\Folder"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => void handleBrowseCustomPath("destination")}
                      disabled={customBrowseLoading !== null}
                    >
                      {customBrowseLoading === "destination" ? (
                        <Loader2 className="animate-spin" size={16} />
                      ) : (
                        <FolderOpen size={16} />
                      )}
                      Browse
                    </Button>
                  </div>
                </div>
              </div>
              <label className="block space-y-2">
                <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  Padrões excluídos
                </span>
                <Input
                  value={customExcludePatterns}
                  onChange={event =>
                    setCustomExcludePatterns(event.target.value)
                  }
                  placeholder="*.ost;*.tmp"
                />
              </label>
            </div>
          )}
        </section>
      )}

      {currentStep === 2 && (
        <section className="space-y-5 rounded-lg border border-border bg-card p-5 shadow-sm">
          {backupMode === "profiles" ? (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-xl font-semibold text-foreground">
                    Seleção de perfis
                  </h2>
                  <p className="mt-1 text-sm text-muted-foreground">
                    {selectedSummary}
                  </p>
                </div>
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={toggleAllUsers}
                  disabled={!availableUsers.length}
                >
                  <RefreshCw size={16} />
                  Alternar todos
                </Button>
              </div>

              {usersWarning && (
                <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-200">
                  {usersWarning}
                </p>
              )}

              {availableUsers.length ? (
                <div className="grid max-h-[420px] gap-2 overflow-auto pr-2 sm:grid-cols-2 lg:grid-cols-3">
                  {availableUsers.map(profile => (
                    <label
                      key={profile}
                      className="flex min-h-11 items-center gap-3 rounded-md border border-border px-3 py-2 text-sm transition-colors hover:bg-muted/50"
                    >
                      <Checkbox
                        checked={selectedUsers.includes(profile)}
                        onCheckedChange={() => toggleUser(profile)}
                      />
                      <span className="min-w-0 truncate font-medium text-foreground">
                        {profile}
                      </span>
                    </label>
                  ))}
                </div>
              ) : (
                <div className="flex min-h-40 flex-col items-center justify-center gap-3 rounded-md border border-dashed border-border text-sm text-muted-foreground">
                  <span>
                    Carregue os usuários da workstation de origem para
                    continuar.
                  </span>
                  <Button
                    variant="outline"
                    className="gap-2"
                    onClick={handleLoadUsers}
                    disabled={!canLoadUsers || loadingUsers}
                  >
                    {loadingUsers ? (
                      <Loader2 className="animate-spin" size={16} />
                    ) : (
                      <Users size={16} />
                    )}
                    Carregar usuários
                  </Button>
                </div>
              )}
            </>
          ) : (
            <>
              <div>
                <h2 className="text-xl font-semibold text-foreground">
                  Confirmação das pastas
                </h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Revise os caminhos antes de seguir para a execução.
                </p>
              </div>
              <div className="grid gap-3 rounded-lg border border-border/70 bg-muted/20 p-4 text-sm md:grid-cols-2">
                <div>
                  <p className="text-muted-foreground">Origem</p>
                  <p className="break-words font-semibold text-foreground">
                    \\\\{normalizeHost(source)}\\{customSourcePath}
                  </p>
                </div>
                <div>
                  <p className="text-muted-foreground">Destino</p>
                  <p className="break-words font-semibold text-foreground">
                    \\\\{normalizeHost(destination)}\\{customDestinationPath}
                  </p>
                </div>
                <div className="md:col-span-2">
                  <p className="text-muted-foreground">Exclusões</p>
                  <p className="break-words font-semibold text-foreground">
                    {customExcludePatterns || "Nenhuma"}
                  </p>
                </div>
              </div>
            </>
          )}
        </section>
      )}

      {currentStep === 3 && (
        <section className="space-y-5 rounded-lg border border-border bg-card p-5 shadow-sm">
          <div>
            <h2 className="text-xl font-semibold text-foreground">
              Revisão e execução
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Faça pre-check ou simulação antes de iniciar o backup.
            </p>
          </div>

          <div className="grid gap-3 rounded-lg border border-border/70 bg-muted/20 p-4 text-sm md:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-muted-foreground">Tipo</p>
              <p className="font-semibold text-foreground">
                {backupMode === "profiles" ? "Perfis" : "Pasta customizada"}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Origem</p>
              <p className="font-semibold text-foreground">
                {normalizeHost(source)}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">Destino</p>
              <p className="font-semibold text-foreground">
                {normalizeHost(destination)}
              </p>
            </div>
            <div>
              <p className="text-muted-foreground">
                {backupMode === "profiles"
                  ? "Perfis selecionados"
                  : "Exclusões"}
              </p>
              <p className="font-semibold text-foreground">
                {backupMode === "profiles"
                  ? `${selectedUsers.length} perfil(is)`
                  : customExcludePatterns || "Nenhuma"}
              </p>
            </div>
            {backupMode === "profiles" && (
              <div className="md:col-span-2 lg:col-span-4">
                <p className="mb-2 text-muted-foreground">Nomes dos perfis</p>
                {selectedUsers.length ? (
                  <div className="flex max-h-24 flex-wrap gap-2 overflow-auto rounded-md border border-border/70 bg-background/60 p-2">
                    {selectedUsers.slice(0, 18).map(profile => (
                      <span
                        key={profile}
                        className="max-w-full truncate rounded-full border border-border bg-card px-2.5 py-1 text-xs font-semibold text-foreground"
                        title={profile}
                      >
                        {profile}
                      </span>
                    ))}
                    {selectedUsers.length > 18 && (
                      <span className="rounded-full border border-border bg-muted px-2.5 py-1 text-xs font-semibold text-muted-foreground">
                        +{selectedUsers.length - 18}
                      </span>
                    )}
                  </div>
                ) : (
                  <p className="rounded-md border border-dashed border-border px-3 py-2 text-sm text-muted-foreground">
                    Nenhum perfil selecionado.
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="flex flex-wrap justify-end gap-3">
            {backupMode === "profiles" && (
              <>
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={handlePrecheck}
                  disabled={!canStartBackup || runningJob || precheckLoading}
                >
                  {precheckLoading ? (
                    <Loader2 className="animate-spin" size={16} />
                  ) : (
                    <CheckCircle2 size={16} />
                  )}
                  Pre-check
                </Button>
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={handleSimulateBackup}
                  disabled={!canStartBackup || runningJob || simulationLoading}
                >
                  {simulationLoading ? (
                    <Loader2 className="animate-spin" size={16} />
                  ) : (
                    <Play size={16} />
                  )}
                  Simular
                </Button>
              </>
            )}
            <Button
              className="gap-2"
              onClick={handleStartBackup}
              disabled={
                !canStartBackup ||
                runningJob ||
                precheckResult?.status === "blocked"
              }
            >
              <Play size={16} />
              Iniciar backup
            </Button>
          </div>

          {precheckResult ? (
            <div
              className={`rounded-md border p-3 text-sm ${precheckResult.status === "ok" ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-800 dark:text-emerald-200" : "border-destructive/40 bg-destructive/10 text-destructive"}`}
            >
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2 font-medium">
                  {precheckResult.status === "ok" ? (
                    <CheckCircle2 size={16} />
                  ) : (
                    <AlertTriangle size={16} />
                  )}
                  {precheckResult.message}
                </div>
                <span>Tamanho estimado: {precheckResult.estimated_size}</span>
              </div>
              <div className="grid gap-2 md:grid-cols-2">
                {precheckResult.checks.map(check => (
                  <div
                    key={`${check.name}-${check.message}`}
                    className="rounded border border-current/20 bg-background/50 px-2 py-1.5"
                  >
                    <p className="font-medium">{check.name}</p>
                    <p className="mt-0.5 text-xs opacity-90">{check.message}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : simulationResult ? (
            <div className="rounded-md border border-blue-500/40 bg-blue-500/10 p-3 text-sm text-blue-900 dark:text-blue-100">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 font-medium">
                <span>{simulationResult.message}</span>
                <span>{simulationResult.planned_items} pasta(s)</span>
              </div>
              <pre className="max-h-72 overflow-auto rounded-md bg-background/70 p-3 font-mono text-xs leading-relaxed">
                {simulationResult.log || "Nenhum log de simulação retornado."}
              </pre>
            </div>
          ) : null}
        </section>
      )}

      {currentStep === 4 && (
        <section className="space-y-5">
          <section className="rounded-lg border border-border bg-card p-5 shadow-sm">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h2 className="text-xl font-semibold text-foreground">
                  Acompanhamento
                </h2>
                <p className="text-sm text-muted-foreground">
                  {visibleActiveJob?.message || "Nenhum backup ativo agora."}
                </p>
              </div>
              {visibleActiveJob && (
                <StatusBadge status={visibleActiveJob.status} />
              )}
            </div>
            <Progress
              value={visibleActiveJob?.progress || 0}
              className="h-2.5"
            />
            <div className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <div>
                <p className="text-muted-foreground">Progresso</p>
                <p className="font-semibold text-foreground">
                  {visibleActiveJob?.progress || 0}%
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Etapa</p>
                <p className="font-semibold text-foreground">
                  {visibleActiveJob?.current_step || 0}/
                  {visibleActiveJob?.total_steps || 0}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">ETA</p>
                <p className="font-semibold text-foreground">
                  {formatEta(visibleActiveJob?.eta_seconds)}
                </p>
              </div>
              <div>
                <p className="text-muted-foreground">Fim estimado</p>
                <p className="font-semibold text-foreground">
                  {formatDateTime(visibleActiveJob?.estimated_end_time)}
                </p>
              </div>
            </div>
            {visibleActiveJob?.status === "running" && (
              <div className="mt-4 flex justify-end">
                <Button
                  variant="outline"
                  className="gap-2"
                  onClick={() => handleCancelBackup(visibleActiveJob.id)}
                >
                  <RotateCcw size={16} />
                  Cancelar
                </Button>
              </div>
            )}
          </section>

          <section className="space-y-4 rounded-lg border border-border bg-card p-5 shadow-sm">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-xl font-semibold text-foreground">
                  Histórico
                </h2>
                <p className="text-sm text-muted-foreground">
                  Jobs recentes e seus estados finais.
                </p>
              </div>
              <div className="flex items-center gap-2">
                {loading && (
                  <Loader2
                    className="animate-spin text-muted-foreground"
                    size={18}
                  />
                )}
                <Button variant="outline" size="sm" onClick={handleRetention}>
                  Limpar antigos
                </Button>
              </div>
            </div>

            {error ? (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            ) : backupJobs.length ? (
              <div className="divide-y divide-border rounded-lg border border-border">
                {backupJobs.map(job => {
                  const isExpanded = expandedJobId === job.id;
                  const detailsJob =
                    isExpanded && visibleActiveJob?.id === job.id
                      ? visibleActiveJob
                      : job;
                  const compactLog = summarizedLog(detailsJob.log);

                  return (
                    <div key={job.id}>
                      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(180px,0.8fr)_minmax(0,1fr)_auto] lg:items-center">
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            <p className="truncate font-semibold text-foreground">
                              {job.workstation}
                            </p>
                            <StatusBadge status={job.status} />
                          </div>
                          <p className="mt-1 truncate text-sm text-muted-foreground">
                            {job.source || job.workstation} para{" "}
                            {job.destination || "destino"}
                          </p>
                        </div>
                        <div className="grid gap-2 text-sm text-muted-foreground md:grid-cols-5">
                          <span>Início: {job.start_time || "--"}</span>
                          <span>Fim: {job.end_time || "--"}</span>
                          <span>Usuários: {job.users?.length || 0}</span>
                          <span>Tamanho: {job.size || "0 GB"}</span>
                          <span>ETA: {formatEta(job.eta_seconds)}</span>
                        </div>
                        <div className="flex justify-end gap-2">
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => handleShowDetails(job)}
                            disabled={loadingDetailsId === job.id}
                          >
                            {loadingDetailsId === job.id ? (
                              <Loader2 className="animate-spin" size={14} />
                            ) : isExpanded ? (
                              "Ocultar"
                            ) : (
                              "Detalhes"
                            )}
                          </Button>
                          {job.status === "running" && (
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => handleCancelBackup(job.id)}
                            >
                              <RotateCcw size={14} />
                            </Button>
                          )}
                          <Button
                            size="sm"
                            variant="destructive"
                            onClick={() => handleDeleteBackup(job.id)}
                          >
                            <Trash2 size={14} />
                          </Button>
                        </div>
                      </div>

                      {isExpanded && (
                        <div className="border-t border-border bg-muted/20 px-4 py-4">
                          <div className="grid gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
                            <div className="space-y-3 text-sm">
                              <div>
                                <p className="text-muted-foreground">Resumo</p>
                                <p className="font-medium text-foreground">
                                  {detailsJob.summary ||
                                    detailsJob.message ||
                                    "Sem resumo disponível."}
                                </p>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() =>
                                    handleOpenJobPath(detailsJob, "source")
                                  }
                                >
                                  <FolderOpen size={14} /> Origem
                                </Button>
                                <Button
                                  size="sm"
                                  variant="outline"
                                  onClick={() =>
                                    handleOpenJobPath(detailsJob, "destination")
                                  }
                                >
                                  <FolderOpen size={14} /> Destino
                                </Button>
                              </div>
                              {detailsJob.failures?.length ? (
                                <div>
                                  <p className="text-muted-foreground">
                                    Falhas
                                  </p>
                                  <div className="mt-1 space-y-1 text-destructive">
                                    {detailsJob.failures
                                      .slice(0, 4)
                                      .map(failure => (
                                        <p key={failure}>{failure}</p>
                                      ))}
                                  </div>
                                </div>
                              ) : null}
                            </div>
                            <div className="min-w-0">
                              <p className="mb-2 text-sm font-medium text-foreground">
                                Log compacto
                              </p>
                              <pre className="max-h-56 overflow-auto rounded-md border border-border bg-background p-3 font-mono text-xs leading-relaxed text-muted-foreground">
                                {compactLog ||
                                  "Nenhum log disponível para este job."}
                              </pre>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="flex min-h-28 items-center justify-center rounded-md border border-dashed border-border text-sm text-muted-foreground">
                Nenhum backup criado ainda.
              </div>
            )}
          </section>
        </section>
      )}
    </>
  );

  return (
    <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden bg-background">
      <main className="h-full min-w-0 flex-1 overflow-auto">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 p-6 lg:p-8">
          <header className="wmt-header relative overflow-hidden rounded-xl border p-5 text-slate-100 shadow-lg">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
              <div>
                <h1 className="text-3xl font-bold text-white">Backup</h1>
                <p className="mt-1 text-sm text-slate-400">
                  Fluxo guiado por etapas para migrar perfis ou copiar uma pasta
                  customizada.
                </p>
              </div>
              <div className="grid grid-cols-3 gap-3 text-sm">
                <div>
                  <p className="text-slate-400">Jobs</p>
                  <p className="text-xl font-semibold text-white">
                    {summary.total}
                  </p>
                </div>
                <div>
                  <p className="text-slate-400">Copiado</p>
                  <p className="text-xl font-semibold text-white">
                    {summary.total_size}
                  </p>
                </div>
                <div>
                  <p className="text-slate-400">Sucesso</p>
                  <p className="text-xl font-semibold text-white">
                    {summary.success_rate}%
                  </p>
                </div>
              </div>
            </div>
          </header>

          <nav className="grid gap-2 md:grid-cols-5">
            {wizardSteps.map((step, index) => {
              const active = currentStep === index;
              const complete = currentStep > index;
              return (
                <button
                  key={step.title}
                  type="button"
                  className={`rounded-lg border px-3 py-3 text-left transition-colors ${
                    active
                      ? "border-primary bg-primary/10"
                      : complete
                        ? "border-emerald-400/40 bg-emerald-500/10"
                        : "border-border bg-card hover:bg-muted/40"
                  }`}
                  onClick={() => setCurrentStep(index)}
                >
                  <div className="flex items-center gap-2">
                    <span
                      className={`flex size-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${active ? "bg-primary text-primary-foreground" : complete ? "bg-emerald-600 text-white" : "bg-muted text-muted-foreground"}`}
                    >
                      {complete ? <CheckCircle2 size={14} /> : index + 1}
                    </span>
                    <span className="text-sm font-semibold text-foreground">
                      {step.title}
                    </span>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {step.description}
                  </p>
                </button>
              );
            })}
          </nav>

          {stepContent}

          <footer className="flex flex-col gap-3 rounded-lg border border-border bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <Button
              variant="outline"
              onClick={goToPreviousStep}
              disabled={currentStep === 0}
            >
              Voltar
            </Button>
            <div className="flex flex-wrap items-center justify-end gap-2">
              {currentStep < 4 ? (
                <Button
                  onClick={goToNextStep}
                  disabled={!canAdvanceFromStep(currentStep)}
                >
                  Próxima etapa
                </Button>
              ) : (
                <Button
                  variant="outline"
                  onClick={() => refetch()}
                  disabled={loading}
                >
                  {loading ? (
                    <Loader2 className="animate-spin" size={16} />
                  ) : (
                    <RefreshCw size={16} />
                  )}
                  Atualizar
                </Button>
              )}
            </div>
          </footer>
        </div>
      </main>
    </div>
  );
}
