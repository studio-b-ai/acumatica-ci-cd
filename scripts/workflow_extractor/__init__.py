"""
Workflow Extractor — Audit Trail → SOPs + Regression Tests

Analyzes Acumatica audit trail data to detect recurring workflow patterns.
When a pattern crosses a configurable threshold (default: 3 occurrences),
auto-generates DOCX SOPs and pytest fixtures.
"""
