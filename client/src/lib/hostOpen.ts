import { invoke } from '@tauri-apps/api/core';

export async function openPathOnHost(path: string) {
  const trimmed = path.trim();
  if (!trimmed) {
    throw new Error('Path is empty.');
  }

  try {
    await invoke('open_path_on_host', { path: trimmed });
    return;
  } catch (error) {
    const isTauriUnavailable =
      !(window as typeof window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;

    if (!isTauriUnavailable) {
      throw error;
    }
  }

  const fileUrl = trimmed.startsWith('\\\\')
    ? `file:${trimmed.replace(/\\/g, '/')}`
    : trimmed;
  const opened = window.open(fileUrl, '_blank', 'noopener,noreferrer');
  if (!opened) {
    throw new Error('Não foi possível abrir a pasta automaticamente fora do app desktop.');
  }
}

export async function openRemoteToolOnHost(action: string, host: string) {
  const trimmedHost = host.trim();
  if (!trimmedHost) {
    throw new Error('Host is empty.');
  }

  try {
    await invoke('open_remote_tool_on_host', { action, host: trimmedHost });
  } catch (error) {
    const isTauriUnavailable =
      !(window as typeof window & { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__;

    if (isTauriUnavailable) {
      throw new Error('Esta ação precisa ser aberta pelo app desktop WMT.');
    }
    throw error;
  }
}
