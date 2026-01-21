// Prevents additional console window on Windows in release, DO NOT REMOVE!!
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use reqwest;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use tauri::{Manager, State};
use tokio::sync::Mutex;

#[derive(Debug, Serialize, Deserialize)]
struct ModelMetrics {
    total_requests: u64,
    success_rate: f64,
    avg_latency: f64,
    avg_rating: f64,
}

#[derive(Debug, Serialize, Deserialize)]
struct DashboardStatus {
    r#type: String,
    timestamp: String,
    strategy: String,
    learning_mode: bool,
    models: HashMap<String, ModelMetrics>,
    summary: SummaryStats,
}

#[derive(Debug, Serialize, Deserialize)]
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

// Learn more about Tauri commands at https://tauri.app/v1/guides/features/command
#[tauri::command]
async fn greet(name: &str) -> String {
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