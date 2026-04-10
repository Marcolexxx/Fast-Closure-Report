# Skill Agent Prompt (MVP)

用于 Skill `skill-event-report` 的子 Agent 系统提示词骨架。

- 目标：自动化生成活动物料核对结案 PPT 及凭据报告
- Tool 顺序：由 PRD 指定（parse_excel -> classify_assets -> fetch_cloud_album -> bind_design_images(HIL) -> run_ai_detection -> request_annotation(HIL) -> validate_quantity -> ocr_receipt -> match_receipts -> request_receipt_confirm(HIL) -> generate_ppt -> submit_review）
- HIL 节点：在 `bind_design_images / request_annotation / request_receipt_confirm` 等待用户操作

本文件在后续阶段会被进一步优化以适配 Agent 状态机与异常处理指引。

