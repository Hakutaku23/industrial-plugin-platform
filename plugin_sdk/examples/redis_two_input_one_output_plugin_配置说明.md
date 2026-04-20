# Redis 二输入一输出测试插件配置说明

插件包名：`redis-two-inputs-one-output-plugin`

## 前端实例配置建议

### 输入绑定
- `input_name = input_014`
- `source_tag = sthb:DCS_AO_RTO_014_AI`

- `input_name = input_015`
- `source_tag = sthb:DCS_AO_RTO_015_AI`

### 输出绑定
- `output_name = output_020`
- `target_tag = sthb:DCS_AO_RTO_020_AI`

## 插件计算公式

```text
output_020 = 0.65 * input_014 + 0.35 * input_015
```

## 例子

当：
- `sthb:DCS_AO_RTO_014_AI = 123.4`
- `sthb:DCS_AO_RTO_015_AI = 56.7`

则：
- `sthb:DCS_AO_RTO_020_AI ≈ 100.0550`

## 说明
这是一个最小可验证插件，便于你在前端完成：
- Redis 取数验证
- 实例输入绑定验证
- 回写绑定验证
- 定时运行验证

后续你可以直接把 `runtime/main.py` 中的计算公式替换成真实模型逻辑。
