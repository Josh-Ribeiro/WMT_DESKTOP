import { Badge } from '@/components/ui/badge';
import { Circle } from 'lucide-react';

interface StatusBadgeProps {
  status: 'online' | 'offline' | 'warning' | 'critical' | 'updating' | 'completed' | 'running' | 'failed' | 'scheduled' | 'canceled';
  label?: string;
}

const statusConfig = {
  online: {
    color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    dotColor: 'text-green-600 dark:text-green-400',
    label: 'Online',
  },
  offline: {
    color: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
    dotColor: 'text-gray-600 dark:text-gray-400',
    label: 'Offline',
  },
  warning: {
    color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200',
    dotColor: 'text-yellow-600 dark:text-yellow-400',
    label: 'Warning',
  },
  critical: {
    color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    dotColor: 'text-red-600 dark:text-red-400',
    label: 'Critical',
  },
  updating: {
    color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    dotColor: 'text-blue-600 dark:text-blue-400',
    label: 'Updating',
  },
  completed: {
    color: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
    dotColor: 'text-green-600 dark:text-green-400',
    label: 'Completed',
  },
  running: {
    color: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
    dotColor: 'text-blue-600 dark:text-blue-400',
    label: 'Running',
  },
  failed: {
    color: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
    dotColor: 'text-red-600 dark:text-red-400',
    label: 'Failed',
  },
  scheduled: {
    color: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200',
    dotColor: 'text-purple-600 dark:text-purple-400',
    label: 'Scheduled',
  },
  canceled: {
    color: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
    dotColor: 'text-gray-600 dark:text-gray-400',
    label: 'Canceled',
  },
};

export function StatusBadge({ status, label }: StatusBadgeProps) {
  const config = statusConfig[status];

  return (
    <div className={`inline-flex items-center gap-2 px-3 py-1 rounded-full ${config.color}`}>
      <Circle size={8} className={`fill-current ${config.dotColor}`} />
      <span className="text-sm font-medium">{label || config.label}</span>
    </div>
  );
}
