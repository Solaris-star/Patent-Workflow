# 双参考源：框架 vs 文风（2026-07-24）

## 用户原话（真源）

> CN121526509A-全文.pdf 这个是**文风参考**，技术交底书框架.docx 是**段落架构参考**。  
> /patent-style 处理过的内容会一直复用的吧，但是我发现之前你连 python 都没复用。

## 错误用法（本会话踩过）

1. 把已填交底书实例（如「基于多智能体协作的项目生命周期管理方法及系统.docx」）当成框架 → 误加【注意事项】/A1B1/替代方案/其他事项。
2. 跳过 `patent-style`，不落 `artifacts/style/*` 就开写 → 结构与文风全靠模型记忆，无法跨会话复用。

## 正确用法

| 输入 | 用途 | 产出 |
|---|---|---|
| `技术交底书框架.docx` | 章节与子节职责 | `template_outline.txt` + `template_rules.json` |
| `CN….pdf` 授权说明书 | 句式、套话、详略 | `reference_patent_text.txt` + `style_profile.md` |

写稿前检查：

```bash
ls artifacts/style/template_rules.json artifacts/style/style_profile.md
```

缺则先跑 patent-style；指纹未变则 `initialization_reused: true` 直接复用。

## 框架正文最小集（无编号）

技术领域；背景（背景知识 / 最接近现有技术 / 缺陷不足）；发明内容（技术问题 / 技术方案 / 技术效果）；专利附图；具体实施方式。

## 文风最小套话（CN 授权案）

- 本发明涉及…特别涉及…
- 本发明的目的在于克服现有技术的不足…
- 为了实现上述目的，本发明采用的技术方案为…
- 本发明的优点在于：1、…2、…3、…
- 下面对照附图，通过对最优实施例的描述…
- 显然本发明具体实现并不受上述方式的限制…

实施效果可学「有量化」的**写法**，但**无数据不得编造**——见 `patent-review-fix-patterns` H0。
