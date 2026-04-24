use std::collections::HashMap;
use std::fs::{self, File};
use std::io::Write;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{
    atomic::{AtomicBool, Ordering},
    Arc, Mutex,
};
use std::thread;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use nix::sys::signal::{killpg, Signal};
use nix::unistd::{setsid, Pid};
use serde::{Deserialize, Serialize};
use wait_timeout::ChildExt;

#[derive(Parser, Debug)]
#[command(name = "ipp_runner_core")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    ExecuteTask,
}

#[derive(Debug, Deserialize)]
struct ExecuteTaskRequest {
    schema_version: String,
    task_id: String,
    run_id: String,
    trigger_type: String,
    environment: String,
    plugin: PluginSpec,
    runtime: RuntimeSpec,
    sandbox: SandboxSpec,
    payload: serde_json::Value,
}

#[derive(Debug, Deserialize)]
struct PluginSpec {
    package_name: String,
    version: String,
    package_dir: String,
    entry_mode: String,
    entry_file: String,
    callable: String,
}

#[derive(Debug, Deserialize)]
struct RuntimeSpec {
    timeout_sec: u64,
    memory_mb: Option<u64>,
    cpu_limit: Option<f64>,
    working_dir: Option<String>,
    env: Option<HashMap<String, String>>,
    filesystem_mode: Option<String>,
    network_enabled: Option<bool>,
    subprocess_enabled: Option<bool>,
}

#[derive(Debug, Deserialize)]
struct SandboxSpec {
    work_root: String,
    task_work_dir: String,
    result_file: String,
    input_file: String,
    cleanup_enabled: Option<bool>,
    cleanup_max_age_sec: Option<u64>,
    cleanup_max_run_dirs: Option<usize>,
    cleanup_min_keep_runs: Option<usize>,
    cleanup_stale_incomplete_age_sec: Option<u64>,
    cleanup_sweep_interval_sec: Option<u64>,
    cleanup_state_file: Option<String>,
}

#[derive(Debug, Serialize)]
struct ExecuteTaskResult {
    schema_version: String,
    task_id: String,
    run_id: String,
    status: String,
    exit_code: i32,
    timing: Timing,
    resource_usage: ResourceUsage,
    plugin_result: PluginResultEnvelope,
    stderr: String,
    error: ErrorPayload,
}

#[derive(Debug, Serialize)]
struct Timing {
    started_at: String,
    finished_at: String,
    wall_time_ms: u128,
}

#[derive(Debug, Serialize)]
struct ResourceUsage {
    peak_rss_mb: u64,
    cpu_time_user_ms: u64,
    cpu_time_system_ms: u64,
    kill_reason: String,
}

#[derive(Debug, Serialize, Default)]
struct PluginResultEnvelope {
    status: String,
    outputs: serde_json::Map<String, serde_json::Value>,
    metrics: serde_json::Map<String, serde_json::Value>,
    logs: Vec<String>,
}

#[derive(Debug, Serialize, Default)]
struct ErrorPayload {
    code: String,
    message: String,
}

#[derive(Debug)]
struct RunDirEntry {
    path: PathBuf,
    modified_epoch_sec: u64,
    has_result: bool,
}

fn main() {
    let result = run();
    match result {
        Ok(output) => {
            println!(
                "{}",
                serde_json::to_string(&output).expect("serialize runner result")
            );
            std::process::exit(0);
        }
        Err(err) => {
            let fallback = ExecuteTaskResult {
                schema_version: "runner-result/v2".to_string(),
                task_id: "unknown".to_string(),
                run_id: "unknown".to_string(),
                status: "infra_error".to_string(),
                exit_code: -1,
                timing: Timing {
                    started_at: iso_now(),
                    finished_at: iso_now(),
                    wall_time_ms: 0,
                },
                resource_usage: ResourceUsage {
                    peak_rss_mb: 0,
                    cpu_time_user_ms: 0,
                    cpu_time_system_ms: 0,
                    kill_reason: "internal".to_string(),
                },
                plugin_result: PluginResultEnvelope::default(),
                stderr: String::new(),
                error: ErrorPayload {
                    code: "E_INTERNAL".to_string(),
                    message: err.to_string(),
                },
            };
            println!(
                "{}",
                serde_json::to_string(&fallback).expect("serialize fallback result")
            );
            std::process::exit(1);
        }
    }
}

fn run() -> Result<ExecuteTaskResult> {
    let cli = Cli::parse();
    match cli.command {
        Commands::ExecuteTask => execute_task(),
    }
}

fn execute_task() -> Result<ExecuteTaskResult> {
    let request: ExecuteTaskRequest = serde_json::from_reader(std::io::stdin())
        .context("failed to parse ExecuteTaskRequest from stdin")?;

    let started_at = iso_now();
    let started_instant = Instant::now();

    validate_request(&request)?;

    let task_work_dir = PathBuf::from(&request.sandbox.task_work_dir);
    maybe_cleanup_work_root(&request, &task_work_dir)?;
    fs::create_dir_all(&task_work_dir).with_context(|| {
        format!(
            "failed to create task work directory: {}",
            task_work_dir.display()
        )
    })?;

    let input_path = task_work_dir.join(&request.sandbox.input_file);
    let result_path = task_work_dir.join(&request.sandbox.result_file);

    let mut input_file = File::create(&input_path)
        .with_context(|| format!("failed to create input file: {}", input_path.display()))?;
    input_file.write_all(
        serde_json::to_string_pretty(&request.payload)
            .context("failed to serialize payload")?
            .as_bytes(),
    )?;

    let package_dir = PathBuf::from(&request.plugin.package_dir);
    let working_dir = resolve_working_dir(&package_dir, request.runtime.working_dir.as_deref());

    let python_exe = std::env::var("IPP_PLUGIN_PYTHON")
        .ok()
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "python".to_string());

    let mut command = Command::new(&python_exe);
    command
        .arg("-m")
        .arg("platform_runner.function_host")
        .arg(package_dir.to_string_lossy().to_string())
        .arg(&request.plugin.entry_file)
        .arg(&request.plugin.callable)
        .current_dir(&working_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    command.env("IPP_INPUT_FILE", input_path.to_string_lossy().to_string());
    command.env("IPP_RESULT_FILE", result_path.to_string_lossy().to_string());
    command.env("PYTHONUNBUFFERED", "1");

    if let Some(extra_env) = &request.runtime.env {
        for (key, value) in extra_env {
            command.env(key, value);
        }
    }

    let memory_limit_bytes = request.runtime.memory_mb.map(|mb| mb * 1024 * 1024);
    unsafe {
        command.pre_exec(move || {
            setsid().map_err(std::io::Error::other)?;
            if let Some(limit) = memory_limit_bytes {
                let rlimit = libc::rlimit {
                    rlim_cur: limit,
                    rlim_max: limit,
                };
                if libc::setrlimit(libc::RLIMIT_AS, &rlimit) != 0 {
                    return Err(std::io::Error::last_os_error());
                }
            }
            Ok(())
        });
    }

    let mut child = command.spawn().context("failed to spawn plugin host")?;
    let child_pid_raw = child.id() as i32;
    let child_pid = Pid::from_raw(child_pid_raw);

    let stop_flag = Arc::new(AtomicBool::new(false));
    let peak_rss_mb = Arc::new(Mutex::new(0_u64));
    let kill_reason = Arc::new(Mutex::new(String::from("none")));

    let monitor_handle = {
        let stop_flag = Arc::clone(&stop_flag);
        let peak_rss_mb = Arc::clone(&peak_rss_mb);
        let kill_reason = Arc::clone(&kill_reason);
        let rss_limit_mb = request.runtime.memory_mb;
        thread::spawn(move || {
            while !stop_flag.load(Ordering::Relaxed) {
                if let Some(rss_mb) = read_peak_rss_mb(child_pid_raw) {
                    if let Ok(mut guard) = peak_rss_mb.lock() {
                        if rss_mb > *guard {
                            *guard = rss_mb;
                        }
                    }
                    if let Some(limit_mb) = rss_limit_mb {
                        if rss_mb > limit_mb {
                            if let Ok(mut reason) = kill_reason.lock() {
                                if reason.as_str() == "none" {
                                    *reason = "memory_limit".to_string();
                                }
                            }
                            let _ = killpg(child_pid, Signal::SIGKILL);
                            break;
                        }
                    }
                }
                thread::sleep(Duration::from_millis(100));
            }
        })
    };

    let timeout = Duration::from_secs(request.runtime.timeout_sec);
    let status = match child.wait_timeout(timeout)? {
        Some(status) => status,
        None => {
            if let Ok(mut reason) = kill_reason.lock() {
                if reason.as_str() == "none" {
                    *reason = "timeout".to_string();
                }
            }
            let _ = killpg(child_pid, Signal::SIGTERM);
            thread::sleep(Duration::from_millis(300));
            let _ = killpg(child_pid, Signal::SIGKILL);
            child.wait().context("failed to wait after timeout kill")?
        }
    };

    let output = child
        .wait_with_output()
        .context("failed to collect child output")?;

    stop_flag.store(true, Ordering::Relaxed);
    let _ = monitor_handle.join();

    let finished_at = iso_now();
    let wall_time_ms = started_instant.elapsed().as_millis();
    let stderr = truncate_utf8(String::from_utf8_lossy(&output.stderr).to_string(), 16 * 1024);
    let stdout = truncate_utf8(String::from_utf8_lossy(&output.stdout).to_string(), 16 * 1024);

    let plugin_result = parse_plugin_result(&result_path, &stdout)?;
    let exit_code = status.code().unwrap_or(-1);

    let kill_reason_value = kill_reason
        .lock()
        .map(|item| item.clone())
        .unwrap_or_else(|_| "none".to_string());

    let mut final_status = if exit_code == 0 && plugin_result.status == "success" {
        "success".to_string()
    } else if kill_reason_value == "timeout" {
        "timeout".to_string()
    } else {
        "failed".to_string()
    };
    if plugin_result.status == "partial_success" && final_status == "success" {
        final_status = "partial_success".to_string();
    }

    let error = if final_status == "success" || final_status == "partial_success" {
        ErrorPayload::default()
    } else {
        ErrorPayload {
            code: map_error_code(&kill_reason_value, exit_code),
            message: if kill_reason_value != "none" {
                format!("plugin process terminated because {}", kill_reason_value)
            } else if !stderr.is_empty() {
                stderr.clone()
            } else {
                format!("plugin process exited with code {}", exit_code)
            },
        }
    };

    Ok(ExecuteTaskResult {
        schema_version: "runner-result/v2".to_string(),
        task_id: request.task_id,
        run_id: request.run_id,
        status: final_status,
        exit_code,
        timing: Timing {
            started_at,
            finished_at,
            wall_time_ms,
        },
        resource_usage: ResourceUsage {
            peak_rss_mb: peak_rss_mb
                .lock()
                .map(|item| *item)
                .unwrap_or_default(),
            cpu_time_user_ms: 0,
            cpu_time_system_ms: 0,
            kill_reason: kill_reason_value,
        },
        plugin_result,
        stderr,
        error,
    })
}

fn validate_request(request: &ExecuteTaskRequest) -> Result<()> {
    if request.schema_version != "runner-task/v1" && request.schema_version != "runner-task/v2" {
        anyhow::bail!("unsupported schema version: {}", request.schema_version);
    }
    if request.plugin.entry_mode != "function" {
        anyhow::bail!("only function plugins are supported in phase 1");
    }
    Ok(())
}

fn maybe_cleanup_work_root(request: &ExecuteTaskRequest, current_task_work_dir: &Path) -> Result<()> {
    if !request.sandbox.cleanup_enabled.unwrap_or(true) {
        return Ok(());
    }

    let work_root = PathBuf::from(&request.sandbox.work_root);
    fs::create_dir_all(&work_root)?;

    let sweep_interval_sec = request.sandbox.cleanup_sweep_interval_sec.unwrap_or(600).max(30);
    let state_file_name = request
        .sandbox
        .cleanup_state_file
        .clone()
        .unwrap_or_else(|| ".runner-cleanup-state".to_string());
    let state_path = work_root.join(state_file_name);
    let now_epoch_sec = unix_now_sec();

    if let Ok(previous) = fs::read_to_string(&state_path) {
        if let Ok(last_cleanup_epoch_sec) = previous.trim().parse::<u64>() {
            if now_epoch_sec.saturating_sub(last_cleanup_epoch_sec) < sweep_interval_sec {
                return Ok(());
            }
        }
    }

    cleanup_run_directories(
        &work_root,
        current_task_work_dir,
        &request.sandbox.result_file,
        request.sandbox.cleanup_max_age_sec.unwrap_or(7 * 24 * 60 * 60),
        request.sandbox.cleanup_max_run_dirs.unwrap_or(500).max(1),
        request.sandbox.cleanup_min_keep_runs.unwrap_or(20),
        request
            .sandbox
            .cleanup_stale_incomplete_age_sec
            .unwrap_or(24 * 60 * 60),
        now_epoch_sec,
    )?;

    let _ = fs::write(state_path, now_epoch_sec.to_string());
    Ok(())
}

fn cleanup_run_directories(
    work_root: &Path,
    current_task_work_dir: &Path,
    result_file_name: &str,
    max_age_sec: u64,
    max_run_dirs: usize,
    min_keep_runs: usize,
    stale_incomplete_age_sec: u64,
    now_epoch_sec: u64,
) -> Result<()> {
    let mut entries: Vec<RunDirEntry> = Vec::new();
    for dir_entry in fs::read_dir(work_root)? {
        let dir_entry = match dir_entry {
            Ok(item) => item,
            Err(_) => continue,
        };
        let path = dir_entry.path();
        if path == current_task_work_dir {
            continue;
        }
        let file_type = match dir_entry.file_type() {
            Ok(value) => value,
            Err(_) => continue,
        };
        if !file_type.is_dir() {
            continue;
        }
        let Some(name) = path.file_name().and_then(|item| item.to_str()) else {
            continue;
        };
        if !name.starts_with("run-") {
            continue;
        }
        let modified_epoch_sec = path_modified_epoch_sec(&path).unwrap_or(0);
        let has_result = path.join(result_file_name).exists();
        entries.push(RunDirEntry {
            path,
            modified_epoch_sec,
            has_result,
        });
    }

    entries.sort_by(|left, right| right.modified_epoch_sec.cmp(&left.modified_epoch_sec));
    let effective_keep_by_count = max_run_dirs.max(min_keep_runs);

    for (index, entry) in entries.into_iter().enumerate() {
        if index < min_keep_runs {
            continue;
        }
        let age_sec = now_epoch_sec.saturating_sub(entry.modified_epoch_sec);
        let over_count_limit = index >= effective_keep_by_count;
        let aged_completed = entry.has_result && age_sec >= max_age_sec;
        let aged_incomplete = !entry.has_result && age_sec >= stale_incomplete_age_sec;
        if !(over_count_limit || aged_completed || aged_incomplete) {
            continue;
        }
        match fs::remove_dir_all(&entry.path) {
            Ok(_) => {}
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
            Err(_) => {}
        }
    }
    Ok(())
}

fn path_modified_epoch_sec(path: &Path) -> Option<u64> {
    let modified = fs::metadata(path).ok()?.modified().ok()?;
    modified.duration_since(UNIX_EPOCH).ok().map(|item| item.as_secs())
}

fn resolve_working_dir(package_dir: &Path, working_dir: Option<&str>) -> PathBuf {
    let candidate = working_dir.unwrap_or(".").trim();
    let joined = package_dir.join(candidate);
    if joined.exists() {
        joined
    } else {
        package_dir.to_path_buf()
    }
}

fn parse_plugin_result(result_path: &Path, stdout: &str) -> Result<PluginResultEnvelope> {
    let raw_text = if result_path.exists() {
        fs::read_to_string(result_path)
            .with_context(|| format!("failed to read result file: {}", result_path.display()))?
    } else {
        stdout.to_string()
    };

    if raw_text.trim().is_empty() {
        anyhow::bail!("plugin result is empty");
    }

    let raw: serde_json::Value =
        serde_json::from_str(&raw_text).context("plugin result is not valid JSON")?;
    let object = raw
        .as_object()
        .context("plugin result must be a JSON object")?;

    let status = object
        .get("status")
        .and_then(|item| item.as_str())
        .unwrap_or("failed")
        .to_string();

    let outputs = object
        .get("outputs")
        .and_then(|item| item.as_object())
        .cloned()
        .unwrap_or_default();

    let metrics = object
        .get("metrics")
        .and_then(|item| item.as_object())
        .cloned()
        .unwrap_or_default();

    let logs = object
        .get("logs")
        .and_then(|item| item.as_array())
        .map(|items| {
            items.iter()
                .map(|item| item.as_str().unwrap_or_default().to_string())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();

    Ok(PluginResultEnvelope {
        status,
        outputs,
        metrics,
        logs,
    })
}

fn map_error_code(kill_reason: &str, exit_code: i32) -> String {
    match kill_reason {
        "timeout" => "E_PROCESS_TIMEOUT".to_string(),
        "memory_limit" => "E_MEMORY_LIMIT_EXCEEDED".to_string(),
        _ if exit_code != 0 => "E_PROCESS_EXIT_NONZERO".to_string(),
        _ => "E_INTERNAL".to_string(),
    }
}

fn read_peak_rss_mb(pid: i32) -> Option<u64> {
    let status_path = format!("/proc/{}/status", pid);
    let content = fs::read_to_string(status_path).ok()?;
    for line in content.lines() {
        if let Some(raw) = line.strip_prefix("VmRSS:") {
            let kb = raw
                .split_whitespace()
                .next()
                .and_then(|value| value.parse::<u64>().ok())?;
            return Some((kb + 1023) / 1024);
        }
    }
    None
}

fn truncate_utf8(mut value: String, max_bytes: usize) -> String {
    if value.len() <= max_bytes {
        return value;
    }
    value.truncate(max_bytes);
    while !value.is_char_boundary(value.len()) {
        value.pop();
    }
    value
}

fn iso_now() -> String {
    format!("{}", unix_now_sec())
}

fn unix_now_sec() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
