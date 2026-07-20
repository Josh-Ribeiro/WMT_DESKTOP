#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{Mutex, OnceLock},
};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

static BACKEND_PROCESS: OnceLock<Mutex<Option<Child>>> = OnceLock::new();

fn backend_process() -> &'static Mutex<Option<Child>> {
    BACKEND_PROCESS.get_or_init(|| Mutex::new(None))
}

fn backend_is_running() -> bool {
    std::net::TcpStream::connect_timeout(
        &"127.0.0.1:8000".parse().expect("valid backend address"),
        std::time::Duration::from_millis(250),
    )
    .is_ok()
}

fn start_backend() {
    if backend_is_running() {
        return;
    }

    let Ok(mut child_slot) = backend_process().lock() else {
        return;
    };
    if child_slot.is_some() {
        return;
    }

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

    let child = Command::new("python")
        .arg(backend_main)
        .current_dir(backend_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn();

    match child {
        Ok(process) => {
            *child_slot = Some(process);
        }
        Err(error) => {
            eprintln!("failed to start backend: {error}");
        }
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

    command.spawn()
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
            command.arg("/c").arg("start").arg("").arg(mstsc).arg(format!("/v:{host}"));
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
            command.arg("/c").arg("start").arg("").arg(msra).arg("/offerra").arg(host);
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
            open_path_on_host,
            open_remote_tool_on_host
        ])
        .setup(|_app| {
            start_backend();
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
