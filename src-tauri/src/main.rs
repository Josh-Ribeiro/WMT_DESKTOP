#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::{
    fs::{self, OpenOptions},
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Mutex, OnceLock},
    time::Duration,
};
use tauri::Manager;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

static BACKEND_PROCESS: OnceLock<Mutex<Option<Child>>> = OnceLock::new();

fn backend_process() -> &'static Mutex<Option<Child>> {
    BACKEND_PROCESS.get_or_init(|| Mutex::new(None))
}

fn backend_mode() -> &'static str {
    if let Ok(mode) = std::env::var("WMT_BACKEND_MODE") {
        if mode.eq_ignore_ascii_case("sidecar") {
            return "sidecar";
        }
        if mode.eq_ignore_ascii_case("central") {
            return "central";
        }
    }
    if let Some(mode) = option_env!("WMT_BACKEND_MODE") {
        if mode.eq_ignore_ascii_case("sidecar") {
            return "sidecar";
        }
        if mode.eq_ignore_ascii_case("central") {
            return "central";
        }
    }
    if cfg!(debug_assertions) {
        "sidecar"
    } else {
        "central"
    }
}

fn local_port_is_open() -> bool {
    std::net::TcpStream::connect_timeout(
        &"127.0.0.1:8000".parse().expect("valid backend address"),
        Duration::from_millis(250),
    )
    .is_ok()
}

#[derive(Deserialize)]
struct BackendHealth {
    status: String,
    service: String,
    api_version: u32,
}

fn local_backend_is_compatible() -> bool {
    let Ok(client) = reqwest::blocking::Client::builder()
        .timeout(Duration::from_millis(750))
        .build()
    else {
        return false;
    };
    let Ok(response) = client.get("http://127.0.0.1:8000/health/live").send() else {
        return false;
    };
    let Ok(health) = response.json::<BackendHealth>() else {
        return false;
    };
    health.status == "ok" && health.service == "wmt-backend" && health.api_version == 1
}

#[cfg(not(debug_assertions))]
fn sidecar_executable(app: &tauri::AppHandle) -> Option<PathBuf> {
    let mut candidates = Vec::new();
    if let Ok(resource_dir) = app.path().resource_dir() {
        candidates.push(resource_dir.join("wmt-backend.exe"));
        candidates.push(resource_dir.join("binaries").join("wmt-backend.exe"));
    }
    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(executable_dir) = current_exe.parent() {
            candidates.push(executable_dir.join("wmt-backend.exe"));
        }
    }
    candidates.into_iter().find(|candidate| candidate.is_file())
}

fn start_backend(app: &tauri::AppHandle) {
    if backend_mode() != "sidecar" {
        return;
    }
    if local_backend_is_compatible() {
        return;
    }
    if local_port_is_open() {
        eprintln!("port 8000 is occupied by a service that is not a compatible WMT backend");
        return;
    }

    let Ok(mut child_slot) = backend_process().lock() else {
        return;
    };
    if child_slot.is_some() {
        return;
    }

    let Ok(data_dir) = app.path().app_data_dir() else {
        eprintln!("failed to resolve the WMT application data directory");
        return;
    };
    let Ok(log_dir) = app.path().app_log_dir() else {
        eprintln!("failed to resolve the WMT log directory");
        return;
    };
    if fs::create_dir_all(&data_dir).is_err() || fs::create_dir_all(&log_dir).is_err() {
        eprintln!("failed to create WMT data or log directory");
        return;
    }
    let Ok(stdout_log) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_dir.join("backend.log"))
    else {
        eprintln!("failed to open the WMT backend log");
        return;
    };
    let Ok(stderr_log) = OpenOptions::new()
        .create(true)
        .append(true)
        .open(log_dir.join("backend-error.log"))
    else {
        eprintln!("failed to open the WMT backend error log");
        return;
    };

    let mut backend_command;
    #[cfg(debug_assertions)]
    {
        let Ok(current_dir) = std::env::current_dir() else {
            return;
        };
        let project_root = if current_dir.join("backend").exists() {
            current_dir
        } else {
            current_dir.parent().unwrap_or(&current_dir).to_path_buf()
        };
        let backend_dir = project_root.join("backend");
        let backend_main = backend_dir.join("main.py");
        if !backend_main.exists() {
            eprintln!("backend/main.py was not found at {:?}", backend_main);
            return;
        }
        backend_command = Command::new("python");
        backend_command.arg(backend_main).current_dir(backend_dir);
    }
    #[cfg(not(debug_assertions))]
    {
        let Some(executable) = sidecar_executable(app) else {
            eprintln!("wmt-backend.exe was not found in the application resources");
            return;
        };
        backend_command = Command::new(executable);
    }

    backend_command
        .env("WMT_BACKEND_HOST", "127.0.0.1")
        .env("WMT_BACKEND_PORT", "8000")
        .env("WMT_DATA_DIR", &data_dir)
        .env("WMT_SESSION_COOKIE_SECURE", "false")
        .env("WMT_SESSION_COOKIE_SAMESITE", "lax")
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout_log))
        .stderr(Stdio::from(stderr_log));

    #[cfg(debug_assertions)]
    backend_command.env("WMT_DEV", "1");
    #[cfg(not(debug_assertions))]
    backend_command.env("WMT_DEV", "0");

    #[cfg(windows)]
    backend_command.creation_flags(CREATE_NO_WINDOW);

    let child = backend_command.spawn();

    match child {
        Ok(process) => {
            *child_slot = Some(process);
        }
        Err(error) => {
            eprintln!("failed to start backend: {error}");
        }
    }
}

#[derive(Serialize)]
struct BackendRuntimeStatus {
    mode: &'static str,
    owned_process: bool,
    local_backend_compatible: bool,
}

#[tauri::command]
fn backend_runtime_status() -> BackendRuntimeStatus {
    let owned_process = backend_process()
        .lock()
        .map(|slot| slot.is_some())
        .unwrap_or(false);
    BackendRuntimeStatus {
        mode: backend_mode(),
        owned_process,
        local_backend_compatible: local_backend_is_compatible(),
    }
}

fn stop_backend() {
    let Ok(mut child_slot) = backend_process().lock() else {
        return;
    };
    if let Some(mut child) = child_slot.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
}

#[tauri::command]
fn open_path_on_host(path: String) -> Result<(), String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err("Path is empty.".to_string());
    }

    if trimmed.starts_with(r"\\") && !std::path::Path::new(trimmed).exists() {
        return Err(format!("Path is not accessible yet: {trimmed}"));
    }

    let mut command = Command::new("explorer.exe");
    command
        .arg(format!("/root,{trimmed}"))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("Failed to open path on host: {error}"))
}

fn validate_remote_host(host: &str) -> Result<&str, String> {
    let trimmed = host.trim();
    if trimmed.is_empty() {
        return Err("Host is empty.".to_string());
    }
    if !trimmed
        .chars()
        .all(|ch| ch.is_ascii_alphanumeric() || matches!(ch, '.' | '_' | '-'))
    {
        return Err("Host contains unsupported characters.".to_string());
    }
    Ok(trimmed)
}

fn validate_web_url(url: &str) -> Result<String, String> {
    let parsed = reqwest::Url::parse(url.trim())
        .map_err(|_| "Web address is invalid.".to_string())?;
    if parsed.scheme() != "http" {
        return Err("Only HTTP addresses are supported for printer configuration.".to_string());
    }
    if !parsed.username().is_empty() || parsed.password().is_some() {
        return Err("Web addresses with embedded credentials are not supported.".to_string());
    }
    let host = parsed
        .host_str()
        .ok_or_else(|| "Web address does not contain a host.".to_string())?;
    validate_remote_host(host)?;
    Ok(parsed.to_string())
}

#[tauri::command]
fn open_web_url(url: String) -> Result<(), String> {
    let url = validate_web_url(&url)?;
    let mut command = Command::new("explorer.exe");
    command
        .arg(url)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    command.creation_flags(CREATE_NO_WINDOW);

    command
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("Failed to open the web address: {error}"))
}

#[tauri::command]
fn open_remote_tool_on_host(action: String, host: String) -> Result<(), String> {
    let host = validate_remote_host(&host)?;
    let action = action.trim().to_ascii_lowercase();

    let mut command = match action.as_str() {
        "remote-access" => {
            let mstsc_path = std::env::var_os("SystemRoot")
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from(r"C:\Windows"))
                .join("System32")
                .join("mstsc.exe");
            let mstsc = if mstsc_path.exists() {
                mstsc_path.to_string_lossy().to_string()
            } else {
                "mstsc.exe".to_string()
            };
            let mut command = Command::new("cmd.exe");
            command
                .arg("/c")
                .arg("start")
                .arg("")
                .arg(mstsc)
                .arg(format!("/v:{host}"));
            command
        }
        "remote-assistance" => {
            let msra_path = std::env::var_os("SystemRoot")
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from(r"C:\Windows"))
                .join("System32")
                .join("msra.exe");
            let msra = if msra_path.exists() {
                msra_path.to_string_lossy().to_string()
            } else {
                "msra.exe".to_string()
            };
            let mut command = Command::new("cmd.exe");
            command
                .arg("/c")
                .arg("start")
                .arg("")
                .arg(msra)
                .arg("/offerra")
                .arg(host);
            command
        }
        "computer-management" => {
            let compmgmt_path = std::env::var_os("SystemRoot")
                .map(PathBuf::from)
                .unwrap_or_else(|| PathBuf::from(r"C:\Windows"))
                .join("System32")
                .join("compmgmt.msc");
            let compmgmt = if compmgmt_path.exists() {
                compmgmt_path.to_string_lossy().to_string()
            } else {
                "compmgmt.msc".to_string()
            };
            let mut command = Command::new("cmd.exe");
            command
                .arg("/c")
                .arg("start")
                .arg("")
                .arg(compmgmt)
                .arg(format!("/computer={host}"));
            command
        }
        _ => return Err(format!("Unsupported local remote tool: {action}")),
    };

    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map(|_| ())
        .map_err(|error| format!("Failed to open remote tool on host: {error}"))
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .invoke_handler(tauri::generate_handler![
            backend_runtime_status,
            open_path_on_host,
            open_web_url,
            open_remote_tool_on_host
        ])
        .setup(|app| {
            start_backend(app.handle());
            Ok(())
        })
        .on_window_event(|_window, event| {
            if matches!(event, tauri::WindowEvent::Destroyed) {
                stop_backend();
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
