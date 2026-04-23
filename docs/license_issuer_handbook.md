# 工业算法插件平台许可证签发操作手册（发行方归档版）

本文档用于发行方长期存档，描述如何为客户部署生成并签发 `license.lic`。

## 1. 一次性准备：生成签发密钥

```bash
python scripts/license_keygen.py --key-id issuer-main-2026 --out-dir issuer_keys
```

生成结果：

- `issuer_keys/issuer-main-2026.private.pem`
- `issuer_keys/issuer-main-2026.public.pem`
- `issuer_keys/issuer-main-2026.public-registry.json`

## 2. 客户侧导出部署指纹

客户登录前端“许可证管理”页面，点击“下载指纹”，得到：

- `license-fingerprint.json`

## 3. 签发永久授权

```bash
python scripts/license_issue.py --key-id issuer-main-2026 --private-key issuer_keys/issuer-main-2026.private.pem --customer-name "某某厂区" --fingerprint-json ./license-fingerprint.json --output ./license.lic --grant-mode perpetual --allow-manual-run true --allow-schedule true --allow-real-writeback true --max-instances 200 --max-packages 200 --max-data-sources 200 --max-concurrent-runs 8 --issuer "Industrial Plugin Platform Issuer"
```

## 4. 签发期限授权

```bash
python scripts/license_issue.py --key-id issuer-main-2026 --private-key issuer_keys/issuer-main-2026.private.pem --customer-name "某某厂区" --fingerprint-json ./license-fingerprint.json --output ./license.lic --grant-mode term --not-before 2026-04-23T00:00:00+00:00 --not-after 2026-04-24T00:00:00+00:00 --allow-manual-run true --allow-schedule true --allow-real-writeback true --max-instances 50 --max-packages 50 --max-data-sources 50 --max-concurrent-runs 4 --issuer "Industrial Plugin Platform Issuer"
```

## 5. 解码核验

```bash
python scripts/license_decode.py --license ./license.lic --output ./license.decoded.json
```
