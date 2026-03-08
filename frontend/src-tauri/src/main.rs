// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use reqwest;
use serde::{Deserialize, Serialize};
use serde_json::json;
use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{Manager, State};
use tokio::sync::Mutex;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ModelMetrics {
    total_requests: u64,
    success_rate: f64,
    avg_latency: f64,
    avg_rating: f64,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct DashboardStatus {
    r#type: String,
    timestamp: String,
    strategy: String,
    learning_mode: bool,
    models: HashMap<String, ModelMetrics>,
    summary: SummaryStats,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct SummaryStats {
    total_requests: u64,
    overall_success_rate: f64,
    overall_avg_latency: f64,
    best_model: Option<String>,
    model_count: usize,
    active_models: usize,
}

struct AppState {
    dashboard_data: Mutex<Option<DashboardStatus>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct CrashReporterConfig {
    upload_opt_in: bool,
    upload_url: Option<String>,
    max_report_bytes: usize,
}

impl Default for CrashReporterConfig {
    fn default() -> Self {
        Self {
            upload_opt_in: false,
            upload_url: None,
            max_report_bytes: 32 * 1024,
        }
    }
}

fn env_bool(name: &str) -> Option<bool> {
    std::env::var(name).ok().map(|value| {
        matches!(
            value.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        )
    })
}

fn load_crash_reporter_config() -> CrashReporterConfig {
    let mut config = CrashReporterConfig::default();

    if let Ok(parsed) = serde_json::from_str::<serde_json::Value>(include_str!("../tauri.conf.json"))
    {
        if let Some(plugin_cfg) = parsed
            .get("plugins")
            .and_then(|plugins| plugins.get("merlinCrashReporter"))
        {
            if let Some(opt_in) = plugin_cfg.get("uploadOptIn").and_then(|value| value.as_bool()) {
                config.upload_opt_in = opt_in;
            }
            if let Some(upload_url) = plugin_cfg.get("uploadUrl").and_then(|value| value.as_str()) {
                let normalized = upload_url.trim();
                if !normalized.is_empty() {
                    config.upload_url = Some(normalized.to_string());
                }
            }
            if let Some(max_bytes) = plugin_cfg
                .get("maxReportBytes")
                .and_then(|value| value.as_u64())
            {
                config.max_report_bytes = std::cmp::max(max_bytes as usize, 1024);
            }
        }
    }

    if let Some(opt_in) = env_bool("MERLIN_CRASH_REPORT_UPLOAD_OPT_IN") {
        config.upload_opt_in = opt_in;
    }
    if let Ok(upload_url) = std::env::var("MERLIN_CRASH_REPORT_UPLOAD_URL") {
        let normalized = upload_url.trim();
        if normalized.is_empty() {
            config.upload_url = None;
        } else {
            config.upload_url = Some(normalized.to_string());
        }
    }
    config
}

fn panic_payload_message(panic_info: &std::panic::PanicHookInfo<'_>) -> String {
    if let Some(message) = panic_info.payload().downcast_ref::<&str>() {
        return (*message).to_string();
    }
    if let Some(message) = panic_info.payload().downcast_ref::<String>() {
        return message.clone();
    }
    "panic payload unavailable".to_string()
}

fn install_crash_reporter_hook(config: CrashReporterConfig, report_dir: PathBuf) {
    let _ = fs::create_dir_all(&report_dir);
    let default_hook = std::panic::take_hook();
    let shared_config = Arc::new(config);
    let shared_report_dir = Arc::new(report_dir);

    std::panic::set_hook(Box::new(move |panic_info| {
        default_hook(panic_info);

        let config = Arc::clone(&shared_config);
        let report_dir = Arc::clone(&shared_report_dir);
        let now_unix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map(|duration| duration.as_secs())
            .unwrap_or(0);
        let location = panic_info
            .location()
            .map(|loc| format!("{}:{}:{}", loc.file(), loc.line(), loc.column()))
            .unwrap_or_else(|| "unknown".to_string());
        let panic_message = panic_payload_message(panic_info);
        let thread_name = std::thread::current().name().unwrap_or("unnamed").to_string();

        let mut report = json!({
            "schema_name": "AAS.TauriCrashReport",
            "schema_version": "1.0.0",
            "timestamp_unix": now_unix,
            "thread": thread_name,
            "message": panic_message,
            "location": location,
        });

        let serialized = serde_json::to_vec_pretty(&report).unwrap_or_default();
        if serialized.len() > config.max_report_bytes {
            report = json!({
                "schema_name": "AAS.TauriCrashReport",
                "schema_version": "1.0.0",
                "timestamp_unix": now_unix,
                "thread": thread_name,
                "message": "Crash report truncated because max_report_bytes was exceeded",
                "location": location,
                "truncated": true,
            });
        }

        let report_filename = format!("crash-report-{}.json", now_unix);
        let report_path = report_dir.join(report_filename);
        if let Ok(report_json) = serde_json::to_string_pretty(&report) {
            let _ = fs::write(&report_path, format!("{report_json}\n"));
        }

        if config.upload_opt_in {
            if let Some(upload_url) = &config.upload_url {
                if !upload_url.trim().is_empty() {
                    let upload_url = upload_url.to_string();
                    std::thread::spawn(move || {
                        let runtime = tokio::runtime::Builder::new_current_thread()
                            .enable_all()
                            .build();
                        if let Ok(runtime) = runtime {
                            let _ = runtime.block_on(async move {
                                let client = reqwest::Client::new();
                                let _ = client.post(upload_url).json(&report).send().await;
                            });
                        }
                    });
                }
            }
        }
    }));
}

// Learn more about Tauri commands at https://tauri.app/v1/guides/features/command
#[tauri::command]
fn greet(name: &str) -> String {
    format!("Hello, {}! You've been greeted from Rust!", name)
}

#[tauri::command]
async fn get_dashboard_status(
    state: State<'_, AppState>,
    api_url: Option<String>,
) -> Result<DashboardStatus, String> {
    let api_base = api_url.unwrap_or_else(|| "http://localhost:8000".to_string());
    
    match reqwest::get(&format!("{}/api/dashboard/status", api_base)).await {
        Ok(response) => {
            match response.json::<DashboardStatus>().await {
                Ok(data) => {
                    *state.dashboard_data.lock().await = Some(data.clone());
                    Ok(data)
                }
                Err(e) => Err(format!("Failed to parse response: {}", e)),
            }
        }
        Err(e) => Err(format!("Failed to fetch dashboard status: {}", e)),
    }
}

#[tauri::command]
async fn get_cached_dashboard_status(
    state: State<'_, AppState>,
) -> Result<Option<DashboardStatus>, String> {
    Ok(state.dashboard_data.lock().await.clone())
}

#[tauri::command]
async fn send_model_request(
    model_name: String,
    prompt: String,
    api_url: Option<String>,
) -> Result<serde_json::Value, String> {
    let api_base = api_url.unwrap_or_else(|| "http://localhost:8000".to_string());
    
    let client = reqwest::Client::new();
    let mut params = HashMap::new();
    params.insert("prompt", prompt);
    params.insert("model", model_name);
    
    match client
        .post(&format!("{}/api/chat", api_base))
        .json(&params)
        .send()
        .await
    {
        Ok(response) => {
            match response.json().await {
                Ok(data) => Ok(data),
                Err(e) => Err(format!("Failed to parse response: {}", e)),
            }
        }
        Err(e) => Err(format!("Failed to send request: {}", e)),
    }
}

fn main() {
    tauri::Builder::default()
        .manage(AppState {
            dashboard_data: Mutex::new(None),
        })
        .invoke_handler(tauri::generate_handler![
            greet,
            get_dashboard_status,
            get_cached_dashboard_status,
            send_model_request
        ])
        .setup(|app| {
            let crash_reporter_config = load_crash_reporter_config();
            let report_dir = app
                .path_resolver()
                .app_data_dir()
                .or_else(|| std::env::current_dir().ok())
                .unwrap_or_else(|| PathBuf::from("."))
                .join("crash-reports");
            install_crash_reporter_hook(crash_reporter_config, report_dir);

            #[cfg(debug_assertions)]
            {
                let window = app.get_window("main").unwrap();
                window.open_devtools();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
