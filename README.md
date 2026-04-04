---
title: CodeFix Arena
emoji: 🚀
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
---


# 🚀 CodeFix Arena — OpenEnv Coding Environment

An agent-first coding environment designed for **debugging, refactoring, and multi-file repair tasks**, built with full OpenEnv-style interaction.

> 🧠 Built for training and evaluating AI agents on real-world software engineering workflows.

---

## 🔥 Overview

CodeFix Arena is a **real-world coding environment** where an AI agent interacts with a workspace using structured actions like:

- reading files
- writing code
- running commands
- analyzing outputs

The agent improves code step-by-step and receives **multi-metric rewards** based on correctness, structure, efficiency, and robustness.

---

## 🎯 Key Features

### 🧠 Agent Interaction (Core)
- `reset()` → initializes a task environment
- `step(action)` → performs actions like file edit / run command
- `state()` → returns current observation

---

### 🧪 Multi-Task Evaluation

| Task | Type | Difficulty | Description |
|------|------|----------|------------|
| Task 1 | Debug | Easy | Fix Python syntax error |
| Task 2 | Refactor | Medium | Remove duplicate logic |
| Task 3 | Multi-file Repair | Hard | Fix Java project across files |

---

### 🧠 Multi-Metric Grading System

Unlike simple pass/fail systems, CodeFix Arena evaluates:

- ✅ Execution success
- ✅ Code correctness
- ✅ Structure & refactoring quality
- ✅ Efficiency (reusability)
- ✅ Robustness (hidden tests)
- ❌ Penalties (bad patterns, infinite loops)

Example breakdown:

```json
{
  "execution": 0.3,
  "correctness": 0.2,
  "structure": 0.15,
  "efficiency": 0.15,
  "penalties": -0.05
}