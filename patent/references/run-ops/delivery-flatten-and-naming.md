# 交付文件命名

正式交付只包含本次请求的终稿和必要附图；审查报告与过程文件留在 artifacts 对应目录。

- 最终题名少于 25 个字，最多 24 字；所有文档和校验器采用同一规则。
- Mermaid-only 是默认附图模式，保留实际引用的 .mmd 源文件；图片只在 manifest 明确选择图片交付时检查。
- DOCX 由指定终稿 Markdown 生成。源 Markdown 保留原位；默认不覆盖既有 DOCX，替换时显式传入 --overwrite。
- 交付门禁绑定 manifest 的输出目录、最终 Markdown 和最新审查的版本哈希。
