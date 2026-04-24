# TDengine 双点位历史窗口测试插件

用于验证平台 TDengine history input binding。

插件输入：

- `history_df`: 平台传入的 `__ipp_type=dataframe` / `orient=split` JSON payload

推荐实例输入绑定：

```json
{
  "binding_type": "history",
  "input_name": "history_df",
  "data_source_id": 1,
  "source_tags": ["DCS_AO_001", "DCS_AO_002"],
  "window": {
    "start_offset_min": 60,
    "end_offset_min": 0,
    "sample_interval_sec": 60,
    "lookback_before_start_sec": 600,
    "fill_method": "ffill_then_interpolate",
    "strict_first_value": true
  }
}
```
