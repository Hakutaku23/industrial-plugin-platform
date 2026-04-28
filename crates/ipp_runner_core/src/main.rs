use std::collections::HashMap;
use std::fs::{self, File};
use std::io::Write;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use anyhow::{Context, Result};
use chrono::{SecondsFormat, Utc};
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
    entry_type: Option<String>,
    entry_file: Option<String>,
    entry_module: Option<String>,
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
    error: ErrorPayload,
}

#[derive(Debug, Serialize, Default, Clone)]
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
                    code: "E_RUNNER_INTERNAL".to_string(),
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

    let entry_type = request.plugin.entry_type.as_deref().unwrap_or("file").trim();
    let entry_ref = match entry_type {
        "module" => request.plugin.entry_module.as_deref().unwrap_or("").trim(),
        _ => request.plugin.entry_file.as_deref().unwrap_or("").trim(),
    };
    if entry_ref.is_empty() {
        anyhow::bail!("plugin entry reference is empty");
    }

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
        .arg(entry_ref)
        .arg(&request.plugin.callable)
        .arg(entry_type)
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
    let max_stderr = request.sandbox.max_stderr_bytes.unwrap_or(16 * 1024);
    let stderr = read_text_tail(&stderr_path, max_stderr).unwrap_or_default();
    let exit_code = status.code().unwrap_or(-1);
    let max_output_json = request.sandbox.max_output_json_bytes.unwrap_or(512 * 1024);
    let (plugin_result, result_error) = match parse_plugin_result(&result_path, max_output_json) {
        Ok(result) => (result, None),
        Err(error) => (
            PluginResultEnvelope {
                status: "failed".to_string(),
                ..PluginResultEnvelope::default()
            },
            Some(error),
        ),
    };

    let final_status = if kill_reason == "timeout" {
        "timeout".to_string()
    } else if exit_code == 0 && plugin_result.status == "success" {
        "success".to_string()
    } else if exit_code == 0 && plugin_result.status == "partial_success" {
        "partial_success".to_string()
    } else {
        "failed".to_string()
    };

    let error = if final_status == "success" || final_status == "partial_success" {
        ErrorPayload::default()
    } else if let Some(parse_error) = result_error {
        parse_error
    } else if !plugin_result.error.code.is_empty() || !plugin_result.error.message.is_empty() {
        plugin_result.error.clone()
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
        anyhow::bail!("only function plugins are supported in this runner version");
    }
    let entry_type = request.plugin.entry_type.as_deref().unwrap_or("file");
    if entry_type != "file" && entry_type != "module" {
        anyhow::bail!("unsupported entry_type: {}", entry_type);
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

fn parse_plugin_result(result_path: &Path, max_output_json_bytes: usize) -> std::result::Result<PluginResultEnvelope, ErrorPayload> {
    if !result_path.exists() {
        return Err(ErrorPayload {
            code: "E_PLUGIN_RESULT_MISSING".to_string(),
            message: "plugin did not produce result.json".to_string(),
        });
    }
    let metadata = fs::metadata(result_path).map_err(|err| ErrorPayload {
        code: "E_PLUGIN_RESULT_UNREADABLE".to_string(),
        message: format!("cannot stat result.json: {}", err),
    })?;
    if metadata.len() as usize > max_output_json_bytes {
        return Err(ErrorPayload {
            code: "E_PLUGIN_RESULT_TOO_LARGE".to_string(),
            message: format!("result.json exceeds max_output_json_bytes: {}", max_output_json_bytes),
        });
    }

    let raw_text = fs::read_to_string(result_path).map_err(|err| ErrorPayload {
        code: "E_PLUGIN_RESULT_UNREADABLE".to_string(),
        message: format!("cannot read result.json: {}", err),
    })?;
    if raw_text.trim().is_empty() {
        return Err(ErrorPayload {
            code: "E_PLUGIN_RESULT_EMPTY".to_string(),
            message: "result.json is empty".to_string(),
        });
    }

    let raw = serde_json::from_str::<serde_json::Value>(&raw_text).map_err(|err| ErrorPayload {
        code: "E_PLUGIN_RESULT_INVALID_JSON".to_string(),
        message: format!("result.json is not valid JSON: {}", err),
    })?;
    let object = raw.as_object().ok_or_else(|| ErrorPayload {
        code: "E_PLUGIN_RESULT_INVALID_SCHEMA".to_string(),
        message: "result.json must contain a JSON object".to_string(),
    })?;

    let status = object
        .get("status")
        .and_then(|item| item.as_str())
        .unwrap_or("failed")
        .to_string();
    if status != "success" && status != "partial_success" && status != "failed" {
        return Err(ErrorPayload {
            code: "E_PLUGIN_RESULT_INVALID_STATUS".to_string(),
            message: format!("unsupported plugin result status: {}", status),
        });
    }
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
    let error = object
        .get("error")
        .and_then(|item| item.as_object())
        .map(|error_object| ErrorPayload {
            code: error_object
                .get("code")
                .and_then(|item| item.as_str())
                .unwrap_or("")
                .to_string(),
            message: error_object
                .get("message")
                .and_then(|item| item.as_str())
                .unwrap_or("")
                .to_string(),
        })
        .unwrap_or_default();

    Ok(PluginResultEnvelope {
        status,
        outputs,
        metrics,
        logs,
        error,
    })
}

fn map_error_code(kill_reason: &str, exit_code: i32, plugin_result: &PluginResultEnvelope) -> String {
    match kill_reason {
        "timeout" => "E_PROCESS_TIMEOUT".to_string(),
        "memory_limit" => "E_MEMORY_LIMIT_EXCEEDED".to_string(),
        _ if exit_code != 0 => "E_PROCESS_EXIT_NONZERO".to_string(),
        _ if plugin_result.status == "failed" => "E_PLUGIN_FAILED".to_string(),
        _ => "E_RUNNER_INTERNAL".to_string(),
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
    if !plugin_result.error.message.trim().is_empty() {
        return plugin_result.error.message.clone();
    }
    if !stderr.trim().is_empty() {
        return stderr.trim().to_string();
    }
    if exit_code != 0 {
        return format!("plugin process exited with code {}", exit_code);
    }
    if plugin_result.status != "success" {
        return "plugin returned failed status".to_string();
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
    Utc::now().to_rfc3339_opts(SecondsFormat::Millis, true)
}
