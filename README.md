# 🚀 CodeFix Arena

An AI-powered coding assistant built on **OpenEnv-style interaction**, designed to debug, refactor, and evaluate code using a structured **agent–environment loop**.

Deployed as an interactive system with **Arena mode (task-based evaluation)** and **Playground mode (free-form coding assistance)**.

---

## 🧠 Overview

CodeFix Arena simulates real-world coding workflows where an intelligent agent:

* Understands tasks
* Interacts with files
* Executes code
* Iteratively improves solutions

The system integrates:

* A **custom coding environment**
* A **multi-metric grader**
* A **tool-based action system**
* A **proxy-compliant LLM interface**

---

## 🎯 Key Features

* 🔧 Debugging and refactoring tasks (Python & Java)
* ⚙️ Multi-step agent interaction (OpenEnv style)
* 📊 Advanced scoring system (strictly within (0,1))
* 🧪 Hidden test validation
* 🌐 Hugging Face deployment
* 🧩 Modular and extensible design

---

## 🔧 Environment Design

### 🧠 Environment Description

The environment simulates a coding workspace where the agent interacts with files and executes code to solve tasks.

Each task includes:

* A problem statement
* Initial buggy or incomplete code
* Expected behavior
* Execution constraints

The agent must iteratively modify the code using available tools and achieve a correct solution.

---

### 🎮 Action Space

The agent operates through the following discrete actions:

* `list_files` → Lists all files in the workspace
* `read_file(path)` → Reads file content
* `write_file(path, content)` → Updates or creates files
* `run_command(command)` → Executes code and captures output

These actions enable a **step-by-step reasoning and correction process**.

---

### 👀 Observation Space

After each action, the agent receives structured observations:

* `stdout` → Program output
* `stderr` → Errors (if any)
* `feedback` → Evaluation feedback
* `reward` → Score (strictly between 0 and 1)
* `state` → Metadata (task type, files, difficulty, etc.)

This feedback loop allows the agent to refine its approach dynamically.

---

### 🎯 Reward Design

The grading system evaluates solutions across multiple dimensions:

* ✅ Execution success
* ✅ Correctness of output
* ✅ Code structure
* ✅ Efficiency and reuse
* ✅ Robustness (hidden tests)
* ❌ Penalties (errors, infinite loops, excessive output)

All scores are normalized strictly within **(0, 1)** to comply with validation constraints.

---

## 🧪 Task Types

* 🐍 Python Debugging
* 🔁 Python Refactoring
* ☕ Java Multi-file Refactoring

Each task increases in complexity and requires multi-step reasoning.

---

## ⚙️ Setup Instructions

### 1️⃣ Clone Repository

```bash
git clone https://github.com/Raj-Borade/CodeFix-Arena.git
cd CodeFix-Arena
```

---

### 2️⃣ Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 3️⃣ Run Application (UI)

```bash
python app.py
```

---

### 4️⃣ Run Evaluation (Baseline)

```bash
python inference.py
```

---

## 🌐 Live Demo

👉 Hugging Face Space:
https://huggingface.co/spaces/rajborade02/codefix-arena

---

## 🧩 System Architecture

* `env/` → Custom coding environment
* `grader.py` → Multi-metric scoring engine
* `inference.py` → Agent execution pipeline
* `app.py` → UI (Gradio-based)

---

## 🔐 API Compliance

The system uses the provided LLM proxy via:

* `API_BASE_URL` (injected environment variable)
* `API_KEY` (injected credential)

No hardcoded API keys are used.

---

## 🚀 Future Improvements

* 🤖 Smarter agent reasoning (chain-of-thought simulation)
* 📈 Leaderboard & benchmarking
* 🧠 Multi-agent collaboration
* 📂 File upload & real-world project fixing

---

## 💡 Why This Project Stands Out

* Combines **LLM + Environment + Evaluation**
* Implements a **true agent loop**
* Goes beyond chatbot → **acts like a coding agent**
* Fully aligned with **OpenEnv principles**

---

## 👨‍💻 Author

**Raj Borade**
Meta x Scaler Hackathon Submission 🚀
