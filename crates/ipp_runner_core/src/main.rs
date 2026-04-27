use std::collections::HashMap;
use std::fs::{self, File};
use std::io::Write;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
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
    max_stdout_bytes: Option<usize>,
    max_stderr_bytes: Option<usize>,
    max_output_json_bytes: Option<usize>,
    max_workdir_total_bytes: Option<usize>,
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

fn main() {
    let started_at = iso_now();
    let started_instant = Instant::now();
    match run() {
        Ok(output) => {
            println!("{}", serde_json::to_string(&output).expect("serialize runner result"));
            std::process::exit(0);
        }
        Err(err) => {
            let finished_at = iso_now();
            let fallback = ExecuteTaskResult {
                schema_version: "runner-result/v2".to_string(),
                task_id: "unknown".to_string(),
                run_id: "unknown".to_string(),
                status: "infra_error".to_string(),
                exit_code: -1,
                timing: Timing {
                    started_at,
                    finished_at,
                    wall_time_ms: started_instant.elapsed().as_millis(),
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
            println!("{}", serde_json::to_string(&fallback).expect("serialize fallback result"));
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
    validate_request(&request)?;

    let started_at = iso_now();
    let started_instant = Instant::now();

    let task_work_dir = PathBuf::from(&request.sandbox.task_work_dir);
    fs::create_dir_all(&task_work_dir).with_context(|| {
        format!("failed to create task work directory: {}", task_work_dir.display())
    })?;

    let input_path = task_work_dir.join(&request.sandbox.input_file);
    let result_path = task_work_dir.join(&request.sandbox.result_file);
    let stdout_path = task_work_dir.join("stdout.log");
    let stderr_path = task_work_dir.join("stderr.log");

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

    let stdout_file = File::create(&stdout_path)
        .with_context(|| format!("failed to create stdout log: {}", stdout_path.display()))?;
    let stderr_file = File::create(&stderr_path)
        .with_context(|| format!("failed to create stderr log: {}", stderr_path.display()))?;

    let mut command = Command::new(&python_exe);
    if let Some(function_host_path) = std::env::var("IPP_FUNCTION_HOST_PATH")
        .ok()
        .filter(|value| !value.trim().is_empty())
    {
        command.arg(function_host_path);
    } else {
        command.arg("-m").arg("platform_runner.function_host");
    }
    command
        .arg(package_dir.to_string_lossy().to_string())
        .arg(&request.plugin.entry_file)
        .arg(&request.plugin.callable)
        .current_dir(&working_dir)
        .stdin(Stdio::null())
        .stdout(Stdio::from(stdout_file))
        .stderr(Stdio::from(stderr_file));

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
    let timeout = Duration::from_secs(request.runtime.timeout_sec);
    let mut kill_reason = String::from("none");

    let status = match child.wait_timeout(timeout)? {
        Some(status) => status,
        None => {
            kill_reason = "timeout".to_string();
            let _ = killpg(child_pid, Signal::SIGTERM);
            thread::sleep(Duration::from_millis(300));
            let _ = killpg(child_pid, Signal::SIGKILL);
            child.wait().context("failed to wait after timeout kill")?
        }
    };

    let finished_at = iso_now();
    let wall_time_ms = started_instant.elapsed().as_millis();
    let max_stdout = request.sandbox.max_stdout_bytes.unwrap_or(16 * 1024);
    let max_stderr = request.sandbox.max_stderr_bytes.unwrap_or(16 * 1024);
    let stdout = read_text_tail(&stdout_path, max_stdout).unwrap_or_default();
    let stderr = read_text_tail(&stderr_path, max_stderr).unwrap_or_default();
    let exit_code = status.code().unwrap_or(-1);
    let plugin_result = parse_plugin_result(&result_path, &stdout);

    let mut final_status = if exit_code == 0 && plugin_result.status == "success" {
        "success".to_string()
    } else if exit_code == 0 && plugin_result.status == "partial_success" {
        "partial_success".to_string()
    } else if kill_reason == "timeout" {
        "timeout".to_string()
    } else {
        "failed".to_string()
    };

    if plugin_result.status == "failed" && exit_code == 0 {
        final_status = "failed".to_string();
    }

    let error = if final_status == "success" || final_status == "partial_success" {
        ErrorPayload::default()
    } else {
        ErrorPayload {
            code: map_error_code(&kill_reason, exit_code, &plugin_result),
            message: error_message(&kill_reason, exit_code, &stderr, &plugin_result),
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
            peak_rss_mb: 0,
            cpu_time_user_ms: 0,
            cpu_time_system_ms: 0,
            kill_reason,
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

fn resolve_working_dir(package_dir: &Path, working_dir: Option<&str>) -> PathBuf {
    let candidate = working_dir.unwrap_or(".").trim();
    let joined = package_dir.join(candidate);
    if joined.exists() {
        joined
    } else {
        package_dir.to_path_buf()
    }
}

fn parse_plugin_result(result_path: &Path, stdout: &str) -> PluginResultEnvelope {
    let raw_text = if result_path.exists() {
        fs::read_to_string(result_path).unwrap_or_default()
    } else {
        stdout.to_string()
    };

    if raw_text.trim().is_empty() {
        return PluginResultEnvelope {
            status: "failed".to_string(),
            ..PluginResultEnvelope::default()
        };
    }

    let Ok(raw) = serde_json::from_str::<serde_json::Value>(&raw_text) else {
        return PluginResultEnvelope {
            status: "failed".to_string(),
            ..PluginResultEnvelope::default()
        };
    };
    let Some(object) = raw.as_object() else {
        return PluginResultEnvelope {
            status: "failed".to_string(),
            ..PluginResultEnvelope::default()
        };
    };

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
            items
                .iter()
                .map(|item| item.as_str().unwrap_or_default().to_string())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();

    PluginResultEnvelope {
        status,
        outputs,
        metrics,
        logs,
    }
}

fn map_error_code(kill_reason: &str, exit_code: i32, plugin_result: &PluginResultEnvelope) -> String {
    match kill_reason {
        "timeout" => "E_PROCESS_TIMEOUT".to_string(),
        "memory_limit" => "E_MEMORY_LIMIT_EXCEEDED".to_string(),
        _ if exit_code != 0 => "E_PROCESS_EXIT_NONZERO".to_string(),
        _ if plugin_result.status != "success" => "E_PLUGIN_FAILED".to_string(),
        _ => "E_INTERNAL".to_string(),
    }
}

fn error_message(
    kill_reason: &str,
    exit_code: i32,
    stderr: &str,
    plugin_result: &PluginResultEnvelope,
) -> String {
    if kill_reason != "none" {
        return format!("plugin process terminated because {}", kill_reason);
    }
    if !stderr.trim().is_empty() {
        return stderr.trim().to_string();
    }
    if exit_code != 0 {
        return format!("plugin process exited with code {}", exit_code);
    }
    if plugin_result.status != "success" {
        return "plugin returned failed status or did not produce result.json".to_string();
    }
    "runner internal error".to_string()
}

fn read_text_tail(path: &Path, max_bytes: usize) -> Option<String> {
    let bytes = fs::read(path).ok()?;
    let start = bytes.len().saturating_sub(max_bytes);
    let mut value = String::from_utf8_lossy(&bytes[start..]).to_string();
    if start > 0 {
        value = format!("...{}", value);
    }
    Some(value)
}

fn iso_now() -> String {
    unix_now_sec().to_string()
}

fn unix_now_sec() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
