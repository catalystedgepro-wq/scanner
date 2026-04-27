# Skill Ingest Hardening Plan

## Owner

- Primary: `Zeno`

## Problem

The external skill ingestion path works, but it is too noisy. The current `ingest_skills.py` pattern is broad enough to re-ingest generated outputs and backups, which bloats the Cerebro knowledge base.

## Current State

- Source tree: `~/skills`
- Ingest script: `~/skills/ingest_skills.py`
- Output: `Cerebro_Knowledge_Base.txt`
- Verified issue:
  - generated knowledge-base text is being re-ingested
  - backup text files can also be re-ingested

## Goal

Keep skill ingestion useful, deterministic, and clean enough that the Cerebro knowledge base remains a high-signal asset.

## Required Changes

### Include

- `SKILL.md`
- meaningful reference docs
- small, high-signal markdown/text documentation

### Exclude

- generated `Cerebro_Knowledge_Base.txt`
- backup files
- huge generated exports
- low-value nested vendor noise

## Acceptance Criteria

- Running the ingest twice should not create compounding duplication
- Generated knowledge-base files are not re-ingested
- Backup artifacts are excluded
- Output remains deterministic enough to diff meaningfully over time

## Suggested Rules

- Skip filenames matching:
  - `Cerebro_Knowledge_Base*.txt`
  - `*.backup.txt`
  - `*.bak`
- Skip hidden/generated folders that are not intended as knowledge sources
- Prefer an allowlist bias over a fully recursive everything-ingest approach

## Follow-on Work

- add a small manifest or config for explicit include/exclude patterns
- document the ingest rules near the script
- version the output intentionally, rather than treating it like a transient dump
