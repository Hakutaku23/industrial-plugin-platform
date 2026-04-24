// Sandbox Phase 2 package note:
// 当前包只提供 runner 强化版的占位覆盖文件说明。
// 由于你当前远端仓库的 Rust runner 已经可稳定运行，建议将真实 main.rs 与本包中的
// docs/sandbox_phase2.md 对照手动合入：
// 1. 增加 max_stdout_bytes / max_stderr_bytes / max_output_json_bytes / max_workdir_total_bytes 解析
// 2. 在执行后统计 result.json 与 workdir 总大小
// 3. 超限时返回 infra_error:
//    - E_STDOUT_LIMIT
//    - E_STDERR_LIMIT
//    - E_OUTPUT_JSON_LIMIT
//    - E_WORKDIR_LIMIT
//
// 为避免你当前稳定 runner 被错误模板覆盖，这个文件故意只做说明，不直接替换实现。
// 请按 docs/sandbox_phase2.md 在现有 runner 上合入。
fn main() {
    println!("This package requires manual merge for crates/ipp_runner_core/src/main.rs");
}
