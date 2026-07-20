import { useEffect, useRef } from 'react';
import { toast } from 'sonner';
import { apiRequest, UnauthorizedError } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';

type Status = 'queued' | 'running' | 'completed' | 'failed' | 'canceled' | string;

interface DashboardJob {
  id: string;
  status: Status;
  source?: string;
  destination?: string;
  host?: string;
  action?: string;
  message?: string;
  summary?: string;
}

interface DashboardSnapshot {
  recent_jobs?: DashboardJob[];
  recent_remote_jobs?: DashboardJob[];
  recent_update_jobs?: DashboardJob[];
}

const ACTIVE_STATUSES = new Set(['queued', 'running']);
const FINAL_STATUSES = new Set(['completed', 'failed', 'canceled']);

function jobKey(kind: string, job: DashboardJob) {
  return `${kind}:${job.id}`;
}

function jobTitle(kind: string, job: DashboardJob) {
  if (kind === 'backup') return `Backup ${job.source || ''} -> ${job.destination || ''}`.trim();
  if (kind === 'remote') return `Task ${job.host || ''}`.trim();
  return `Update ${job.host || ''}`.trim();
}

function toastFor(kind: string, job: DashboardJob) {
  const title = jobTitle(kind, job);
  const description = job.message || job.summary || job.id;
  if (job.status === 'completed') {
    toast.success(`${title} completed`, { description });
  } else if (job.status === 'failed') {
    toast.error(`${title} failed`, { description });
  } else if (job.status === 'canceled') {
    toast.warning(`${title} canceled`, { description });
  }
}

export default function OperationalNotifier() {
  const { user, loading } = useAuth();
  const previousStatuses = useRef<Map<string, Status>>(new Map());
  const initialized = useRef(false);

  useEffect(() => {
    if (loading || !user) {
      return;
    }

    let stopped = false;
    let inFlight = false;
    let timeoutId: number | undefined;

    const scheduleNext = (delay: number) => {
      if (!stopped) {
        timeoutId = window.setTimeout(checkJobs, delay);
      }
    };

    const checkJobs = async () => {
      if (stopped || inFlight) {
        return;
      }
      if (document.hidden) {
        scheduleNext(20000);
        return;
      }
      inFlight = true;
      let nextDelay = 20000;
      try {
        const snapshot = await apiRequest<DashboardSnapshot>('/api/operational-jobs');
        if (stopped) return;

        const jobs = [
          ...(snapshot.recent_jobs || []).map((job) => ({ kind: 'backup', job })),
          ...(snapshot.recent_remote_jobs || []).map((job) => ({ kind: 'remote', job })),
          ...(snapshot.recent_update_jobs || []).map((job) => ({ kind: 'update', job })),
        ];
        if (jobs.some(({ job }) => ACTIVE_STATUSES.has(job.status))) {
          nextDelay = 5000;
        }
        const nextStatuses = new Map(previousStatuses.current);

        for (const { kind, job } of jobs) {
          const key = jobKey(kind, job);
          const previous = previousStatuses.current.get(key);
          if (
            initialized.current &&
            previous &&
            ACTIVE_STATUSES.has(previous) &&
            FINAL_STATUSES.has(job.status)
          ) {
            toastFor(kind, job);
          }
          nextStatuses.set(key, job.status);
        }

        previousStatuses.current = nextStatuses;
        initialized.current = true;
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          stopped = true;
        }
      } finally {
        inFlight = false;
        scheduleNext(nextDelay);
      }
    };

    void checkJobs();
    const handleVisibility = () => {
      if (!document.hidden) {
        if (timeoutId) window.clearTimeout(timeoutId);
        void checkJobs();
      }
    };
    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      stopped = true;
      if (timeoutId) window.clearTimeout(timeoutId);
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [loading, user]);

  return null;
}
