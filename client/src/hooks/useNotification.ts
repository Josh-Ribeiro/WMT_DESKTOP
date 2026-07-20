import { useCallback } from 'react';
import { toast } from 'sonner';

export type NotificationType = 'success' | 'error' | 'info' | 'warning';

interface NotificationOptions {
  duration?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export function useNotification() {
  const notify = useCallback(
    (message: string, type: NotificationType = 'info', options?: NotificationOptions) => {
      const toastOptions = {
        duration: options?.duration || 3000,
        action: options?.action,
      };

      switch (type) {
        case 'success':
          toast.success(message, toastOptions);
          break;
        case 'error':
          toast.error(message, toastOptions);
          break;
        case 'warning':
          toast.warning(message, toastOptions);
          break;
        case 'info':
        default:
          toast.info(message, toastOptions);
          break;
      }
    },
    []
  );

  const success = useCallback(
    (message: string, options?: NotificationOptions) => notify(message, 'success', options),
    [notify]
  );

  const error = useCallback(
    (message: string, options?: NotificationOptions) => notify(message, 'error', options),
    [notify]
  );

  const warning = useCallback(
    (message: string, options?: NotificationOptions) => notify(message, 'warning', options),
    [notify]
  );

  const info = useCallback(
    (message: string, options?: NotificationOptions) => notify(message, 'info', options),
    [notify]
  );

  return { notify, success, error, warning, info };
}
