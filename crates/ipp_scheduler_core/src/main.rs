use std::sync::Arc;
use std::time::Duration;

use anyhow::Result;
use clap::{Parser, Subcommand};
use reqwest::header::{HeaderMap, HeaderValue};
use reqwest::Client;
use serde::{Deserialize, Serialize};
use tokio::sync::Semaphore;

#[derive(Parser, Debug)]
#[command(name = "ipp_scheduler_core")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]
enum Commands {
    Daemon {
        #[arg(long)]
        config_json: String,
    },
}

#[derive(Debug, Deserialize, Clone)]
struct SchedulerConfig {
    base_url: String,
    internal_token: String,
    tick_interval_ms: u64,
    idle_min_interval_ms: u64,
    idle_max_interval_ms: u64,
    error_backoff_ms: u64,
    max_due_batch: usize,
    max_parallel_dispatch: usize,
    request_timeout_sec: u64,
    worker_id: String,
}

#[derive(Debug, Deserialize, Default)]
struct DueResponse {
    items: Vec<DueItem>,
    next_due_in_ms: Option<u64>,
    suggested_poll_interval_ms: Option<u64>,
    recovered_count: Option<u64>,
}

#[derive(Debug, Deserialize, Clone)]
struct DueItem {
    id: i64,
    scheduled_for: String,
    schedule_interval_sec: i64,
}

#[derive(Debug, Serialize)]
struct ClaimRequest {
    instance_id: i64,
    scheduled_for: String,
    worker_id: String,
}

#[derive(Debug, Deserialize)]
struct ClaimResponse {
    claimed: bool,
    lease_key: Option<String>,
    lease_token: Option<String>,
    claimed_at: Option<String>,
}

#[derive(Debug, Serialize)]
struct ExecuteRequest {
    instance_id: i64,
    worker_id: String,
    scheduled_for: String,
    claimed_at: Option<String>,
}

#[derive(Debug, Serialize)]
struct CompleteRequest {
    instance_id: i64,
    lease_key: String,
    lease_token: String,
    worker_id: String,
}

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();
    match cli.command {
        Commands::Daemon { config_json } => daemon(config_json).await?,
    }
    Ok(())
}

async fn daemon(config_json: String) -> Result<()> {
    let config: SchedulerConfig = serde_json::from_str(&config_json)?;
    let client = build_client(&config)?;
    let semaphore = Arc::new(Semaphore::new(config.max_parallel_dispatch.max(1)));
    let mut next_sleep_ms = 0_u64;

    loop {
        if next_sleep_ms > 0 {
            tokio::time::sleep(Duration::from_millis(next_sleep_ms)).await;
        }

        let due_response = match fetch_due_items(&client, &config).await {
            Ok(response) => response,
            Err(err) => {
                eprintln!("scheduler due fetch failed: {err}");
                next_sleep_ms = config.error_backoff_ms.max(config.tick_interval_ms.max(50));
                continue;
            }
        };

        let sleep_after_cycle = compute_next_sleep_ms(&config, &due_response);
        for item in due_response.items {
            let permit = match semaphore.clone().acquire_owned().await {
                Ok(permit) => permit,
                Err(_) => continue,
            };
            let client = client.clone();
            let config = config.clone();
            tokio::spawn(async move {
                let _permit = permit;
                let _ = process_due_item(client, config, item).await;
            });
        }

        next_sleep_ms = sleep_after_cycle;
    }
}

fn build_client(config: &SchedulerConfig) -> Result<Client> {
    let mut headers = HeaderMap::new();
    headers.insert(
        "x-ipp-internal-token",
        HeaderValue::from_str(&config.internal_token)?,
    );
    Ok(Client::builder()
        .default_headers(headers)
        .timeout(Duration::from_secs(config.request_timeout_sec.max(2)))
        .build()?)
}

async fn fetch_due_items(client: &Client, config: &SchedulerConfig) -> Result<DueResponse> {
    let url = format!(
        "{}/api/v1/internal/scheduler/due?limit={}&worker_id={}",
        config.base_url.trim_end_matches('/'),
        config.max_due_batch.max(1),
        config.worker_id
    );
    let response = client.get(url).send().await?.error_for_status()?;
    let payload: DueResponse = response.json().await?;
    Ok(payload)
}

fn compute_next_sleep_ms(config: &SchedulerConfig, payload: &DueResponse) -> u64 {
    if !payload.items.is_empty() {
        return config.tick_interval_ms.max(50);
    }

    let idle_min = config.idle_min_interval_ms.max(100);
    let idle_max = config.idle_max_interval_ms.max(idle_min);
    if let Some(suggested) = payload.suggested_poll_interval_ms {
        return suggested.clamp(50, idle_max);
    }
    if let Some(next_due) = payload.next_due_in_ms {
        return next_due.clamp(50, idle_max);
    }
    idle_max
}

async fn process_due_item(client: Client, config: SchedulerConfig, item: DueItem) -> Result<()> {
    let claim_url = format!(
        "{}/api/v1/internal/scheduler/claim",
        config.base_url.trim_end_matches('/')
    );
    let claim_response = client
        .post(claim_url)
        .json(&ClaimRequest {
            instance_id: item.id,
            scheduled_for: item.scheduled_for.clone(),
            worker_id: config.worker_id.clone(),
        })
        .send()
        .await?
        .error_for_status()?
        .json::<ClaimResponse>()
        .await?;

    if !claim_response.claimed {
        return Ok(());
    }

    let execute_url = format!(
        "{}/api/v1/internal/scheduler/execute",
        config.base_url.trim_end_matches('/')
    );
    let _ = client
        .post(execute_url)
        .json(&ExecuteRequest {
            instance_id: item.id,
            worker_id: config.worker_id.clone(),
            scheduled_for: item.scheduled_for.clone(),
            claimed_at: claim_response.claimed_at.clone(),
        })
        .send()
        .await?
        .error_for_status()?;

    let complete_url = format!(
        "{}/api/v1/internal/scheduler/complete",
        config.base_url.trim_end_matches('/')
    );
    if let (Some(lease_key), Some(lease_token)) =
        (claim_response.lease_key, claim_response.lease_token)
    {
        let _ = client
            .post(complete_url)
            .json(&CompleteRequest {
                instance_id: item.id,
                lease_key,
                lease_token,
                worker_id: config.worker_id.clone(),
            })
            .send()
            .await?
            .error_for_status()?;
    }

    Ok(())
}
