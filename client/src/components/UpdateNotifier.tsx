import { useEffect, useRef } from "react";
import type { DownloadEvent, Update } from "@tauri-apps/plugin-updater";
import { toast } from "sonner";

function isTauriRuntime() {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

function formatBytes(bytes: number) {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 MB";
  }

  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

async function installUpdate(update: Update) {
  let downloaded = 0;
  let total: number | undefined;
  const toastId = toast.loading(`Downloading WMT ${update.version}...`);

  try {
    await update.downloadAndInstall((event: DownloadEvent) => {
      if (event.event === "Started") {
        total = event.data.contentLength;
      }

      if (event.event === "Progress") {
        downloaded += event.data.chunkLength;
        const suffix = total
          ? `${formatBytes(downloaded)} / ${formatBytes(total)}`
          : formatBytes(downloaded);
        toast.loading(`Downloading WMT ${update.version} (${suffix})`, {
          id: toastId,
        });
      }

      if (event.event === "Finished") {
        toast.loading("Installing update...", { id: toastId });
      }
    });

    toast.success("Update installed. Restart WMT to finish.", { id: toastId });
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    toast.error(`Update failed: ${message}`, { id: toastId });
  }
}

function showUpdateToast(update: Update) {
  toast.info(`WMT ${update.version} is available`, {
    description: update.body ? (
      <div className="max-h-48 overflow-y-auto whitespace-pre-line pr-1">
        {update.body}
      </div>
    ) : (
      `Current version: ${update.currentVersion}`
    ),
    duration: Infinity,
    action: {
      label: "Update now",
      onClick: () => {
        void installUpdate(update);
      },
    },
  });
}

export default function UpdateNotifier() {
  const checked = useRef(false);

  useEffect(() => {
    if (checked.current || !isTauriRuntime()) {
      return;
    }

    checked.current = true;

    const checkForUpdates = async () => {
      try {
        const { check } = await import("@tauri-apps/plugin-updater");
        const update = await check({ timeout: 15000 });
        if (update) {
          showUpdateToast(update);
        }
      } catch (error) {
        console.info("WMT updater check skipped:", error);
      }
    };

    void checkForUpdates();
  }, []);

  return null;
}
