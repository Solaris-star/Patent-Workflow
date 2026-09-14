# 标题夹交付布局（2026-07-24）

用户：「过程产物都存进专利名的文件夹，没有就创建」。

```
<output_dir>/<标题>/
├── <标题>技术交底书.md
├── <标题>技术交底书.docx
├── 附图/
│   ├── fig_01_*.mmd
│   ├── fig_01_*.png      # health_check 要 image 时
│   ├── fig_02_*.mmd
│   └── fig_02_*.png
└── artifacts/
    ├── research/         # pack + evidence/*
    ├── prior_art/
    ├── style/            # patent-style 四件
    ├── draft/            # part_* + merged + facts_ledger
    ├── audit/
    ├── revision/         # backup + post_fix
    ├── delivery/         # health report + 终稿副本
    ├── archive/          # 错误模板残留
    └── run_manifest.md
```

## facts_ledger 图件

```json
"artifacts": {
  "mmd": "附图/fig_01_系统架构.mmd",
  "image": "附图/fig_01_系统架构.png",
  "editable": ["附图/fig_01_系统架构.mmd"]
}
```

caption 与正文「系统架构框图 / 方法工作流程框图」逐字一致。

## 健康检查

```bash
# 优先 venv（有 python-docx）
<home> \
  …/patent/scripts/health_check_delivery_package.py \
  --deliver-dir "<标题夹>" --patent-title "<标题>" \
  --facts-ledger artifacts/draft/facts_ledger.json \
  --consistency-report artifacts/audit/phase_08_consistency_audit_report.md \
  --ipr-report artifacts/audit/phase_09_ipr_review_report.md \
  --out artifacts/delivery/phase_11_delivery_health_report.json \
  --base-dir "<标题夹>"
```

staging 吸收后删除 `_staging_*`。