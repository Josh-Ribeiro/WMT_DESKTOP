export type JobStatus =
  | "queued"
  | "running"
  | "completed"
  | "failed"
  | "canceled"
  | string;

export interface DashboardActivity {
  id: string;
  action: string;
  username: string;
  details?: Record<string, unknown>;
  timestamp: string;
}

export interface DashboardBackupJob {
  id: string;
  source: string;
  destination: string;
  users: number;
  status: JobStatus;
  progress: number;
  start_time: string;
  end_time: string;
  summary: string;
}

export interface DashboardRemoteJob {
  id: string;
  host: string;
  action: string;
  status: JobStatus;
  ok: boolean;
  message: string;
  created_by: string;
  created_at: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
}

export interface DashboardUpdateJob {
  id: string;
  host: string;
  status: JobStatus;
  ok: boolean;
  message: string;
  created_by: string;
  created_at: string;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  progress: number;
  pending_updates: number;
}

export interface DashboardData {
  terms_today: number;
  active_users: number;
  backup_summary: {
    total: number;
    running: number;
    completed: number;
    failed: number;
    canceled: number;
    finished_today: number;
  };
  remote_summary?: {
    total: number;
    active: number;
    completed: number;
    failed: number;
  };
  update_summary?: {
    total: number;
    active: number;
    completed: number;
    failed: number;
  };
  recent_activities: DashboardActivity[];
  recent_jobs: DashboardBackupJob[];
  recent_remote_jobs?: DashboardRemoteJob[];
  recent_update_jobs?: DashboardUpdateJob[];
  trends?: {
    days: Array<{
      date: string;
      label: string;
      total: number;
      completed: number;
      failed: number;
    }>;
  };
}
