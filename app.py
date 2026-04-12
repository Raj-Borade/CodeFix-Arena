import html
import os
import re
from typing import Any, Dict, List, Optional

import gradio as gr
import uvicorn
from fastapi import Body, FastAPI
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from env.coding_env import CodingAssistantEnv
from env.runtime_debugger import RuntimeDebugger

env = CodingAssistantEnv()
AGENT_TRACE = []
LAST_STATE: Dict[str, Any] = {}


def sanitize_info_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return {}

    clean = {}

    for k, v in data.items():
        key = str(k).lower()

        if key in {
            "reward",
            "scores",
            "average_score",
            "step",
            "max_steps",
            "current_step",
            "done",
        }:
            continue

        if isinstance(v, (int, float, bool)):
            continue

        if isinstance(v, dict):
            clean[k] = sanitize_info_payload(v)
        else:
            clean[k] = v

    return clean


def safe_reward(value: Any) -> float:
    try:
        value = float(value)
    except Exception:
        return 0.01

    if value != value:
        return 0.01

    if value >= 1.0:
        return 0.95
    if value <= 0.0:
        return 0.01

    return max(0.01, min(0.95, value))


class ResetRequest(BaseModel):
    task_id: Optional[int] = None


class ActionRequest(BaseModel):
    tool: str
    path: Optional[str] = None
    content: Optional[str] = None
    command: Optional[str] = None


class CommandResultModel(BaseModel):
    status: str = ""
    stdout: str = ""
    stderr: str = ""


class ObservationModel(BaseModel):
    task_id: int
    task_type: str
    difficulty: str
    language: str
    title: str
    step: int
    max_steps: int
    workspace_dir: str
    files: List[str]
    last_command_result: CommandResultModel


class StepResponseModel(BaseModel):
    observation: ObservationModel
    reward: float
    done: bool
    info: Dict[str, Any] = Field(default_factory=dict)


def to_jsonable(data: Any) -> Any:
    return jsonable_encoder(data)


def model_to_dict(model: Any) -> Dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_none=True)
    if hasattr(model, "dict"):
        return model.dict(exclude_none=True)
    return {}


def build_observation_model(state: Dict[str, Any]) -> ObservationModel:
    last_command_result = state.get("last_command_result") or {}
    return ObservationModel(
        task_id=int(state.get("task_id", 0)),
        task_type=str(state.get("task_type", "")),
        difficulty=str(state.get("difficulty", "")),
        language=str(state.get("language", "")),
        title=str(state.get("title", "")),
        step=int(state.get("step", 0)),
        max_steps=int(state.get("max_steps", 0)),
        workspace_dir=str(state.get("workspace_dir", "")),
        files=list(state.get("files", [])),
        last_command_result=CommandResultModel(
            status=str(last_command_result.get("status", "")),
            stdout=str(last_command_result.get("stdout", "")),
            stderr=str(last_command_result.get("stderr", "")),
        ),
    )


def snapshot_state(state: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    global LAST_STATE

    if state is not None:
        LAST_STATE = state
        return to_jsonable(state)

    try:
        if hasattr(env, "state") and callable(getattr(env, "state")):
            current = env.state()
            LAST_STATE = current
            return to_jsonable(current)
    except Exception:
        pass

    return to_jsonable(LAST_STATE)


def format_task_info(state):
    return (
        f"Task ID: {state.get('task_id', 'N/A')}\n"
        f"Type: {state.get('task_type', 'N/A')}\n"
        f"Difficulty: {state.get('difficulty', 'N/A')}\n"
        f"Language: {state.get('language', 'N/A')}\n"
        f"Title: {state.get('title', 'N/A')}\n"
        f"Step: {state.get('step', 0)} / {state.get('max_steps', 0)}"
    )


def format_status(message, reward=None, done=None, extra=None):
    lines = [message]
    if reward is not None:
        lines.append(f"Reward: {reward}")
    if done is not None:
        lines.append(f"Done: {done}")
    if extra:
        lines.append(extra)
    return "\n".join(lines)


def get_suggested_fix_code(task_id):
    task_id = int(task_id)

    if task_id == 1:
        return """def add(a, b):
    return a + b

print(add(2, 3))
"""
    elif task_id == 2:
        return """def calculate_total():
    total = 0
    total += 100
    total += 50
    return total

def process_order():
    print(calculate_total())

def process_cart():
    print(calculate_total())

process_order()
process_cart()
"""
    elif task_id == 3:
        return """public class CalculatorService {
    public int add(int a, int b) {
        return a + b;
    }
}
"""
    return ""


def build_agent_trace(trace_steps):
    if not trace_steps:
        return "No agent actions yet."

    formatted = []
    for idx, step in enumerate(trace_steps):
        formatted.append(f"Step {idx + 1} -> {step}")
    return "\n".join(formatted)


def build_agent_thinking(trace_steps):
    if not trace_steps:
        return "No reasoning steps yet."

    blocks = []
    for idx, step in enumerate(trace_steps):
        blocks.append(
            f"### Step {idx + 1}\n"
            f"- Action: {step}"
        )
    return "\n\n".join(blocks)


def reset_trace():
    global AGENT_TRACE
    AGENT_TRACE = []


def load_task_console(task_id):
    reset_trace()

    try:
        state = env.reset(task_id=int(task_id))
        snapshot_state(state)
        AGENT_TRACE.append(f"Loaded task {state['task_id']} ({state['title']}).")

        files = state.get("files", [])
        first_file = files[0] if files else ""
        file_content = ""

        if first_file:
            try:
                file_content = env.workspace.read_file(first_file)
                AGENT_TRACE.append(f"Auto-opened first file: {first_file}.")
            except Exception as e:
                file_content = f"Error reading initial file: {e}"
                AGENT_TRACE.append(f"Failed to auto-open file: {first_file}. Error: {e}")

        default_command = env.current_task.get("run_command", "") if env.current_task else ""

        task_info = format_task_info(state)
        file_list = "\n".join(files)

        status = format_status(
            "Task loaded successfully.",
            reward=f"{safe_reward(0.01):.3f}",
            done=False,
            extra="Workspace initialized and ready for agent interaction."
        )

        score_breakdown = {
            "status": "loaded",
            "action": "load_task",
            "file": first_file if first_file else "",
        }

        verdict = (
            "Agent Verdict:\n"
            "- Workspace initialized\n"
            "- First file loaded\n"
            "- Ready to inspect, edit, and execute"
        )

        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            task_info,
            file_list,
            first_file,
            file_content,
            default_command,
            status,
            "",
            "",
            f"{safe_reward(0.01):.3f}",
            "",
            score_breakdown,
            build_agent_trace(AGENT_TRACE),
            verdict,
            thinking,
        )

    except Exception as e:
        AGENT_TRACE.append(f"Failed to load task. Error: {e}")
        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            "Task failed to load.",
            "",
            "",
            "",
            "",
            format_status("Task loading failed.", reward=f"{safe_reward(0.01):.3f}", done=False, extra=str(e)),
            "",
            "",
            f"{safe_reward(0.01):.3f}",
            str(e),
            {"error": str(e)},
            build_agent_trace(AGENT_TRACE),
            "Agent Verdict:\n- Task loading failed",
            thinking,
        )


def list_files_console():
    try:
        files = env.workspace.list_files()
        AGENT_TRACE.append("Listed workspace files.")
        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            "\n".join(files),
            format_status("Workspace file list refreshed.", reward=f"{safe_reward(0.01):.3f}", done=False),
            build_agent_trace(AGENT_TRACE),
            thinking,
        )
    except Exception as e:
        AGENT_TRACE.append(f"Failed to list files. Error: {e}")
        thinking = build_agent_thinking(AGENT_TRACE)
        return (
            "",
            format_status("Failed to list files.", reward=f"{safe_reward(0.01):.3f}", done=False, extra=str(e)),
            build_agent_trace(AGENT_TRACE),
            thinking,
        )


def read_file_console(path):
    path = (path or "").strip()
    if not path:
        return (
            "",
            "Please enter a file path.",
            build_agent_trace(AGENT_TRACE),
            build_agent_thinking(AGENT_TRACE),
        )

    try:
        content = env.workspace.read_file(path)
        AGENT_TRACE.append(f"Read file: {path}.")
        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            content,
            format_status("File read successfully.", reward=f"{safe_reward(0.01):.3f}", done=False),
            build_agent_trace(AGENT_TRACE),
            thinking,
        )
    except Exception as e:
        AGENT_TRACE.append(f"Failed to read file: {path}. Error: {e}")
        thinking = build_agent_thinking(AGENT_TRACE)
        return (
            "",
            format_status("File read failed.", reward=f"{safe_reward(0.01):.3f}", done=False, extra=str(e)),
            build_agent_trace(AGENT_TRACE),
            thinking,
        )


def write_file_console(path, content):
    path = (path or "").strip()
    if not path:
        return (
            "Please enter a file path.",
            {},
            build_agent_trace(AGENT_TRACE),
            "Agent Verdict:\n- No file selected",
            build_agent_thinking(AGENT_TRACE),
        )

    try:
        message = env.workspace.write_file(path, content or "")
        AGENT_TRACE.append(f"Wrote updated content to {path}.")
        safe = safe_reward(0.01)

        score_breakdown = {
            "status": "updated",
            "action": "write_file",
            "file": path,
        }

        verdict = (
            "Agent Verdict:\n"
            f"- File updated: {path}\n"
            f"- Reward impact: {safe:.3f}\n"
            f"- Episode done: False"
        )

        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            format_status(message or "Write completed.", reward=f"{safe:.3f}", done=False),
            score_breakdown,
            build_agent_trace(AGENT_TRACE),
            verdict,
            thinking,
        )
    except Exception as e:
        AGENT_TRACE.append(f"Failed to write file: {path}. Error: {e}")
        thinking = build_agent_thinking(AGENT_TRACE)
        return (
            format_status("Write failed.", reward=f"{safe_reward(0.01):.3f}", done=False, extra=str(e)),
            {"error": str(e)},
            build_agent_trace(AGENT_TRACE),
            "Agent Verdict:\n- File write failed",
            thinking,
        )




def normalize_workspace_command(command: str) -> str:
    command = str(command or "").strip()
    if not command:
        return ""

    # Preserve valid absolute interpreter paths exactly as entered.
    # These are commonly required on local Windows setups.
    if re.match(r'^\s*"?[A-Za-z]:\.*python(?:w)?\.exe"?(?:\s+.*)?$', command, flags=re.IGNORECASE):
        return command

    # Only normalize launcher-style commands that do not use an absolute path.
    command = re.sub(r'^\s*"?python(?:w)?\.exe"?(?=\s|$)', 'python', command, flags=re.IGNORECASE)
    command = re.sub(r'^\s*"?py(?:\.exe)?"?(?=\s|$)', 'py', command, flags=re.IGNORECASE)

    return command.strip()


def extract_command_result(info: Any, state: Dict[str, Any]) -> Dict[str, str]:
    info = info or {}
    state = state or {}

    result = info.get("tool_result", {}) if isinstance(info, dict) else {}
    state_result = state.get("last_command_result", {}) if isinstance(state, dict) else {}

    if not isinstance(result, dict):
        result = {}
    if not isinstance(state_result, dict):
        state_result = {}

    merged = {
        "status": str(result.get("status") or state_result.get("status") or ""),
        "stdout": str(result.get("stdout") or state_result.get("stdout") or ""),
        "stderr": str(result.get("stderr") or state_result.get("stderr") or ""),
    }

    if not merged["status"]:
        if merged["stdout"] and not merged["stderr"]:
            merged["status"] = "success"
        elif merged["stderr"]:
            merged["status"] = "error"
        else:
            merged["status"] = "unknown"

    return merged

def run_command_console(command):
    raw_command = str(command or "").strip()
    command = normalize_workspace_command(raw_command)

    if not command:
        return (
            "",
            "",
            f"{safe_reward(0.01):.3f}",
            "Please enter a command to run.",
            "Command not executed.",
            {},
            build_agent_trace(AGENT_TRACE),
            "Agent Verdict:\n- No command provided",
            build_agent_thinking(AGENT_TRACE),
        )

    try:
        state, reward, done, info = env.step({
            "tool": "run_command",
            "command": command,
        })
        snapshot_state(state)

        info = info or {}
        result = extract_command_result(info, state)
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        feedback = info.get("feedback", "") if isinstance(info, dict) else ""
        safe = safe_reward(reward)

        AGENT_TRACE.append(f"Ran command: {command}.")
        if raw_command != command:
            AGENT_TRACE.append(f"Normalized command from: {raw_command}")
        AGENT_TRACE.append(f"Command status: {result.get('status', 'unknown')}.")

        extra_lines = []
        if raw_command != command:
            extra_lines.append(f"Normalized Command: {command}")
        extra_lines.append(f"Expected Fix: {info.get('expected_fix', 'N/A') if isinstance(info, dict) else 'N/A'}")

        status = format_status(
            f"Command status: {result.get('status', 'unknown')}",
            reward=f"{safe:.3f}",
            done=done,
            extra="\n".join(extra_lines),
        )

        score_breakdown = info.get("score_breakdown", {}) if isinstance(info, dict) else {}
        if not score_breakdown:
            score_breakdown = {
                "status": "executed",
                "action": "run_command",
                "command": command,
                "command_status": result.get("status", "unknown"),
            }
        elif isinstance(score_breakdown, dict):
            score_breakdown = dict(score_breakdown)
            score_breakdown.setdefault("command", command)
            score_breakdown["command_status"] = result.get("status", score_breakdown.get("command_status", "unknown"))

        if not feedback:
            if stdout:
                feedback = "Command executed and produced console output."
            elif stderr:
                feedback = "Command executed with runtime or compile feedback."
            else:
                feedback = "Command executed, but no visible console output was returned."

        verdict = (
            "Agent Verdict:\n"
            f"- Execution: {result.get('status', 'unknown')}\n"
            f"- Reward: {safe:.3f}\n"
            f"- Feedback: {feedback if feedback else 'No feedback'}"
        )

        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            stdout,
            stderr,
            f"{safe:.3f}",
            feedback,
            status,
            score_breakdown,
            build_agent_trace(AGENT_TRACE),
            verdict,
            thinking,
        )
    except Exception as e:
        AGENT_TRACE.append(f"Command run failed: {raw_command}. Error: {e}")
        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            "",
            str(e),
            f"{safe_reward(0.01):.3f}",
            "Command execution failed.",
            format_status("Command failed.", reward=f"{safe_reward(0.01):.3f}", done=False, extra=str(e)),
            {"error": str(e)},
            build_agent_trace(AGENT_TRACE),
            "Agent Verdict:\n- Command execution failed",
            thinking,
        )

def ask_assistant_console(task_id, file_content, user_message):
    task_id = int(task_id)
    msg = (user_message or "").strip()
    lower_msg = msg.lower()

    if not (file_content or "").strip():
        return (
            "Hey — I don't have any file content loaded yet.\n\n"
            "Load a task first, then read the file, and I'll help you properly."
        )

    greeting_words = ["hi", "hello", "hey", "yo", "hii", "good morning", "good evening"]
    if any(word in lower_msg for word in greeting_words) and len(lower_msg.split()) <= 4:
        if task_id == 1:
            return (
                "Hey Raj\n\n"
                "I'm ready. This one looks like a small debugging task. "
                "Send me what you want help with — bug, fix, explanation, or next step."
            )
        elif task_id == 2:
            return (
                "Hello Raj\n\n"
                "I'm ready to help. This task looks more like a cleanup/refactor problem. "
                "Ask me what feels confusing and we'll go step by step."
            )
        else:
            return (
                "Hey Raj\n\n"
                "I'm here. This task is a Java multi-file refactor, so we'll need to fix logic and method usage carefully. "
                "Ask me anything."
            )

    if any(x in lower_msg for x in ["i don't understand", "dont understand", "confused", "stuck", "help me", "what to do"]):
        if task_id == 1:
            return (
                "No stress — this one is actually small.\n\n"
                "First look at the function definition. "
                "The main thing I'd inspect is whether the syntax is complete there. "
                "After that, run the file once and we'll verify the output."
            )
        elif task_id == 2:
            return (
                "You're fine — this is more of a design issue than a scary bug.\n\n"
                "Try spotting repeated logic first. "
                "If two functions are doing almost the same calculation, that repeated part should usually become a helper function."
            )
        else:
            return (
                "You're not stuck — this task is asking you to repair a Java project across multiple files.\n\n"
                "Think of it like this: one file has wrong logic, and another may have the wrong method usage. "
                "We want the whole project to compile and print the correct final output."
            )

    if any(x in lower_msg for x in ["what is wrong", "what's wrong", "wats wrong", "error", "bug", "issue", "problem"]):
        if task_id == 1:
            return (
                "The main issue is in the function definition.\n\n"
                "It looks like Python syntax is incomplete there — specifically, the function line should end properly before the block starts. "
                "That's the first thing I would fix."
            )
        elif task_id == 2:
            return (
                "Nothing is crashing here in the usual sense — the issue is structural.\n\n"
                "The code repeats the same logic in multiple places, which makes it harder to maintain. "
                "So the problem is duplication, not syntax."
            )
        else:
            return (
                "The main issue is that the Java project is not behaving correctly as a whole.\n\n"
                "Usually that means either the core logic is wrong, or one class is calling or formatting something incorrectly. "
                "So we need to inspect more than one file."
            )

    if any(x in lower_msg for x in ["how to fix", "fix it", "correct it", "solution", "give fix", "how do i fix"]):
        if task_id == 1:
            return (
                "I'd fix it like this:\n\n"
                "```python\n"
                "def add(a, b):\n"
                "    return a + b\n\n"
                "print(add(2, 3))\n"
                "```\n\n"
                "After that, run the command and check whether the output becomes `5`."
            )
        elif task_id == 2:
            return (
                "A cleaner version would be:\n\n"
                "```python\n"
                "def calculate_total():\n"
                "    total = 0\n"
                "    total += 100\n"
                "    total += 50\n"
                "    return total\n\n"
                "def process_order():\n"
                "    print(calculate_total())\n\n"
                "def process_cart():\n"
                "    print(calculate_total())\n\n"
                "process_order()\n"
                "process_cart()\n"
                "```\n\n"
                "This keeps behavior the same, but removes repetition."
            )
        else:
            return (
                "For this Java task, I'd inspect all three files, then fix the logic first and the method usage second.\n\n"
                "A common correct end state is:\n\n"
                "```java\n"
                "public class CalculatorService {\n"
                "    public int add(int a, int b) {\n"
                "        return a + b;\n"
                "    }\n"
                "}\n"
                "```\n\n"
                "Then make sure the formatter method name matches what `Main.java` expects, and run the full compile command."
            )

    if any(x in lower_msg for x in ["next", "next step", "what should i do", "what now", "what to do next"]):
        if task_id == 1:
            return (
                "Next step: correct the function definition, write the file, and run the command.\n\n"
                "If output becomes `5`, you're basically done."
            )
        elif task_id == 2:
            return (
                "Next step: create the helper function first.\n\n"
                "Once that exists, replace the repeated logic in the other functions with calls to it, then run the file."
            )
        else:
            return (
                "Next step: read all Java files first.\n\n"
                "Then fix the wrong logic, check the formatter method name, and run the full compile-and-run command."
            )

    if any(x in lower_msg for x in ["why", "explain", "reason", "how does this work"]):
        if task_id == 1:
            return (
                "Because Python is strict about function syntax.\n\n"
                "If the function declaration line is incomplete, Python stops before it can even run the body. "
                "So syntax must be fixed before anything else matters."
            )
        elif task_id == 2:
            return (
                "Because repeated logic is risky.\n\n"
                "If you ever want to change that calculation later, you'd have to update it in multiple places. "
                "A helper function keeps that logic in one place."
            )
        else:
            return (
                "Because Java multi-file tasks depend on coordination between classes.\n\n"
                "One file can have correct syntax but still fail overall if another file has wrong logic or the wrong method name."
            )

    if any(x in lower_msg for x in ["thanks", "thank you", "nice", "great", "good", "awesome"]):
        return (
            "Anytime, Raj\n\n"
            "You're actually building this well. "
            "Test it once more after each change and you'll keep the demo stable."
        )

    if task_id == 1:
        return (
            "Here's how I'm seeing it:\n\n"
            "This looks like a straightforward debug task. "
            "I'd first make sure the function syntax is valid, then run the file immediately to confirm the output.\n\n"
            "Ask me whether you want the bug explained, the fix written, or the next action."
        )
    elif task_id == 2:
        return (
            "My read on this one is: the code probably works, but it's not structured well.\n\n"
            "So instead of hunting for a crash, I'd improve the design by reducing duplication. "
            "I can help you identify exactly what should be extracted."
        )
    else:
        return (
            "This one is a Java multi-file refactor task.\n\n"
            "So I'd think in terms of checking how the classes interact, then fixing the smallest number of lines needed so the project compiles and prints the expected output."
        )


def auto_fix_console(task_id, current_path):
    current_path = (current_path or "").strip()
    fixed_code = get_suggested_fix_code(task_id)

    if not current_path:
        return (
            "",
            "No file path selected.",
            {},
            build_agent_trace(AGENT_TRACE),
            "Agent Verdict:\n- No file path selected",
            build_agent_thinking(AGENT_TRACE),
        )

    try:
        message = env.workspace.write_file(current_path, fixed_code)
        AGENT_TRACE.append(f"Auto-fix applied to {current_path}.")
        safe = safe_reward(0.01)

        score_breakdown = {
            "status": "updated",
            "action": "auto_fix_write",
            "file": current_path,
        }

        verdict = (
            "Agent Verdict:\n"
            "- Suggested fix generated\n"
            f"- File updated: {current_path}\n"
            f"- Reward impact: {safe:.3f}\n"
            f"- Episode done: False"
        )

        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            fixed_code,
            f"{message}\nReward: {safe:.3f}\nDone: False",
            score_breakdown,
            build_agent_trace(AGENT_TRACE),
            verdict,
            thinking,
        )
    except Exception as e:
        AGENT_TRACE.append(f"Auto-fix failed for {current_path}. Error: {e}")
        thinking = build_agent_thinking(AGENT_TRACE)
        return (
            "",
            f"Auto-fix failed.\nError: {e}",
            {"error": str(e)},
            build_agent_trace(AGENT_TRACE),
            "Agent Verdict:\n- Auto-fix failed",
            thinking,
        )


def _extract_error_line(language: str, stderr: str) -> Optional[int]:
    if not stderr:
        return None

    language = (language or "").lower().strip()

    if language == "python":
        match = re.search(r"line\s+(\d+)", stderr)
        if match:
            return int(match.group(1))

    if language == "java":
        match = re.search(r"Main\.java:(\d+)", stderr)
        if match:
            return int(match.group(1))

    if language == "cpp":
        match = re.search(r":(\d+):\d+:", stderr)
        if match:
            return int(match.group(1))

    return None


def _line_reason(language: str, line: str) -> str:
    clean = (line or "").strip()

    if not clean:
        return "Blank line skipped."

    if clean.startswith("import ") or clean.startswith("#include"):
        return "Import/include is prepared before execution continues."

    if clean.startswith("def ") or clean.startswith("class "):
        return "Definition is registered in memory."

    if clean.startswith("public class") or clean.startswith("class "):
        return "Class structure is prepared."

    if clean.startswith("if ") or clean.startswith("elif ") or clean.startswith("else"):
        return "A condition is evaluated here."

    if clean.startswith("for ") or clean.startswith("while "):
        return "A loop starts or continues here."

    if clean.startswith("return"):
        return "A value is returned from the current scope."

    if "print(" in clean or "System.out.println" in clean or "cout" in clean:
        return "This line sends output to the console."

    if "=" in clean and "==" not in clean and "!=" not in clean and ">=" not in clean and "<=" not in clean:
        return "A variable is assigned or updated here."

    if "(" in clean and ")" in clean:
        return "A function or method call is triggered here."

    return "This line is evaluated in sequence."


def _simulation_header_badge(status: str) -> str:
    normalized = str(status or "completed").strip().lower()

    if normalized in {"error", "failed", "failure", "compile_error", "runtime_error"}:
        return '<span class="sim-badge sim-badge-error">ERROR DETECTED</span>'
    if normalized in {"success", "ok", "completed", "pass", "passed"}:
        return '<span class="sim-badge sim-badge-success">TRACE COMPLETED</span>'

    return '<span class="sim-badge sim-badge-running">SIMULATED RUN</span>'


def _simulation_thinking_state(status: str) -> str:
    normalized = str(status or "running").strip().lower()

    if normalized in {"error", "failed", "failure", "compile_error", "runtime_error"}:
        label = "Thinking stopped at the failure point"
    elif normalized in {"success", "ok", "completed", "pass", "passed"}:
        label = "Thinking completed across the execution path"
    else:
        label = "Thinking through the execution path"

    return (
        '<div class="sim-thinking-row">'
        '<span class="sim-thinking-pulse"></span>'
        f'<span class="sim-thinking-copy">{html.escape(label)}</span>'
        '<span class="sim-thinking-dots"><span></span><span></span><span></span></span>'
        '</div>'
    )


def _build_phase_cards(status: str, error_line: Optional[int], stdout: str, stderr: str) -> str:
    has_error = error_line is not None or bool((stderr or "").strip())
    phases = [
        ("Initialize", "Workspace and runtime settings prepared.", "done"),
        ("Parse Code", "Language structure and syntax shape inspected.", "done"),
        ("Simulate Flow", "Execution path is walked top-to-bottom.", "current"),
        (
            "Finalize",
            "Execution ends with output or an error stop.",
            "error" if has_error else "success",
        ),
    ]

    cards = ['<div class="sim-phase-grid">']
    for title, desc, state in phases:
        cards.append(
            f'<div class="sim-phase-card sim-phase-{state}">'
            f'<div class="sim-phase-title">{html.escape(title)}</div>'
            f'<div class="sim-phase-desc">{html.escape(desc)}</div>'
            '</div>'
        )
    cards.append('</div>')
    return ''.join(cards)


def build_simulation_trace(language: str, code: str, stdout: str, stderr: str) -> str:
    language = str(language or "python").strip().lower()
    code = str(code or "")
    stdout = str(stdout or "")
    stderr = str(stderr or "")

    if not code.strip():
        return """
        <div class="sim-shell">
            <div class="sim-shell-header">
                <div>
                    <div class="sim-shell-title">Execution Intelligence</div>
                    <div class="sim-shell-subtitle">Run the simulator to see how the code likely moved through execution.</div>
                </div>
                <span class="sim-badge sim-badge-running">WAITING</span>
            </div>
            <div class="sim-thinking-row sim-thinking-row-waiting">
                <span class="sim-thinking-pulse"></span>
                <span class="sim-thinking-copy">Thinking will animate here when the live trace opens.</span>
                <span class="sim-thinking-dots"><span></span><span></span><span></span></span>
            </div>
            <div class="sim-empty-state">No code available for simulation yet.</div>
        </div>
        """

    lines = code.splitlines()
    error_line = _extract_error_line(language, stderr)
    non_empty_lines = [line for line in lines if line.strip()]
    status = "error" if error_line is not None or stderr.strip() else "success"
    header_badge = _simulation_header_badge(status)

    cards: List[str] = []
    cards.append('<div class="sim-shell">')
    cards.append('<div class="sim-shell-header">')
    cards.append('<div>')
    cards.append('<div class="sim-shell-title">Execution Intelligence</div>')
    cards.append('<div class="sim-shell-subtitle">Live-style reasoning for how the current program likely executed.</div>')
    cards.append('</div>')
    cards.append(header_badge)
    cards.append('</div>')
    cards.append(_simulation_thinking_state(status))

    cards.append('<div class="sim-meta-strip">')
    cards.append(f'<div class="sim-meta-pill"><span>Language</span><strong>{html.escape(language.upper())}</strong></div>')
    cards.append(f'<div class="sim-meta-pill"><span>Active lines</span><strong>{len(non_empty_lines)}</strong></div>')
    cards.append(f'<div class="sim-meta-pill"><span>Error line</span><strong>{error_line if error_line is not None else "None"}</strong></div>')
    cards.append('</div>')

    cards.append(_build_phase_cards(status, error_line, stdout, stderr))

    cards.append('<div class="sim-section-title">Execution Timeline</div>')

    visited_any = False

    for idx, line in enumerate(lines, start=1):
        if not line.strip():
            continue

        visited_any = True
        state_class = "sim-step-active"
        state_label = "SIMULATED"

        if error_line is not None and idx == error_line:
            state_class = "sim-step-error"
            state_label = "STOPPED HERE"
        elif error_line is None and idx == len(lines):
            state_class = "sim-step-success"
            state_label = "COMPLETED"

        cards.append(f'<div class="sim-step-card {state_class}">')
        cards.append('<div class="sim-step-top">')
        cards.append(f'<div class="sim-step-line">Line {idx}</div>')
        cards.append(f'<div class="sim-step-state">{html.escape(state_label)}</div>')
        cards.append('</div>')
        cards.append(f'<pre class="sim-code-block"><code>{html.escape(line)}</code></pre>')
        cards.append(f'<div class="sim-step-reason">{html.escape(_line_reason(language, line))}</div>')
        cards.append('</div>')

        if error_line is not None and idx == error_line:
            cards.append('<div class="sim-stop-card">')
            cards.append('<div class="sim-stop-title">Execution stopped at this point.</div>')
            cards.append('<div class="sim-stop-desc">The runtime likely failed on this line or immediately after it, so the simulated trace ends here.</div>')
            if stderr.strip():
                cards.append(f'<pre class="sim-terminal-block"><code>{html.escape(stderr.strip())}</code></pre>')
            cards.append('</div>')
            cards.append('</div>')
            return ''.join(cards)

    if not visited_any:
        cards.append('<div class="sim-empty-state">The file contains only blank lines, so there is no execution path to simulate.</div>')
        cards.append('</div>')
        return ''.join(cards)

    cards.append('<div class="sim-section-title">Final Result</div>')

    if stdout.strip():
        cards.append('<div class="sim-result-card sim-result-success">')
        cards.append('<div class="sim-result-title">Program output</div>')
        cards.append(f'<pre class="sim-terminal-block"><code>{html.escape(stdout.strip())}</code></pre>')
        cards.append('</div>')
    elif stderr.strip():
        cards.append('<div class="sim-result-card sim-result-error">')
        cards.append('<div class="sim-result-title">Runtime / compile details</div>')
        cards.append(f'<pre class="sim-terminal-block"><code>{html.escape(stderr.strip())}</code></pre>')
        cards.append('</div>')
    else:
        cards.append('<div class="sim-result-card sim-result-neutral">')
        cards.append('<div class="sim-result-title">Execution summary</div>')
        cards.append('<div class="sim-result-copy">The program completed without visible console output.</div>')
        cards.append('</div>')

    cards.append('</div>')
    return ''.join(cards)


def close_simulation_drawer():
    return gr.update(visible=False)


def run_playground(language, code):
    result = RuntimeDebugger.analyze_code(language, code)

    summary = (
        f"Status: {result['status']}\n"
        f"Message: {result['message']}\n"
        f"Hint: {result['hint']}"
    )

    return summary, result["stdout"], result["stderr"]


def run_playground_simulation(language, code):
    language = str(language or "python")
    code = str(code or "")

    result = RuntimeDebugger.analyze_code(language, code)

    summary = (
        f"Status: {result['status']}\n"
        f"Message: {result['message']}\n"
        f"Hint: {result['hint']}"
    )

    trace = build_simulation_trace(
        language=language,
        code=code,
        stdout=result["stdout"],
        stderr=result["stderr"],
    )

    return (
        summary,
        result["stdout"],
        result["stderr"],
        gr.update(visible=True),
        trace,
    )


def detect_language_from_filename(filename):
    ext = os.path.splitext(filename.lower())[1]

    if ext == ".py":
        return "python"
    if ext == ".java":
        return "java"
    if ext in [".cpp", ".cc", ".cxx", ".c"]:
        return "cpp"
    return "python"


def import_playground_file(file_path):
    if not file_path:
        return "python", "", "No file selected."

    try:
        language = detect_language_from_filename(file_path)

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="latin-1") as f:
                content = f.read()

        summary = (
            f"Imported file successfully.\n"
            f"Filename: {os.path.basename(file_path)}\n"
            f"Detected Language: {language}"
        )

        return language, content, summary

    except Exception as e:
        return "python", "", f"Failed to import file.\nError: {e}"


def create_demo():
    with gr.Blocks(title="CodeFix Arena") as demo:
        gr.HTML("""
        <style>
            :root {
                --cf-bg: #050505;
                --cf-bg-soft: #0a0a0a;
                --cf-panel: #0d0d0d;
                --cf-panel-2: #111111;
                --cf-panel-3: #151515;
                --cf-border: rgba(255, 255, 255, 0.08);
                --cf-border-strong: rgba(255, 255, 255, 0.14);
                --cf-text: #f5f5f5;
                --cf-text-soft: #b5b5b5;
                --cf-text-muted: #8b8b8b;
                --cf-accent: #7eb6ff;
                --cf-accent-soft: rgba(126, 182, 255, 0.12);
                --cf-success: #7de2b4;
                --cf-error: #ff8c8c;
                --cf-warning: #e5c07b;
                --cf-shadow: 0 14px 36px rgba(0, 0, 0, 0.45);
            }

            html, body, .gradio-container {
                background: var(--cf-bg) !important;
                color: var(--cf-text) !important;
            }

            .gradio-container {
                font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
            }

            .gradio-container .block,
            .gradio-container .gr-box,
            .gradio-container .gr-panel,
            .gradio-container .gr-form,
            .gradio-container .gr-group,
            .gradio-container .gr-accordion,
            .gradio-container .gradio-group,
            .gradio-container .gradio-html,
            .gradio-container .gradio-json,
            .gradio-container .gradio-markdown {
                background: var(--cf-panel) !important;
                border: 1px solid var(--cf-border) !important;
                box-shadow: none !important;
            }

            .gradio-container .contain,
            .gradio-container .wrap,
            .gradio-container .gap {
                background: transparent !important;
            }

            .gradio-container h1,
            .gradio-container h2,
            .gradio-container h3,
            .gradio-container h4,
            .gradio-container label,
            .gradio-container .prose,
            .gradio-container .prose * {
                color: var(--cf-text) !important;
            }

            .gradio-container .prose p,
            .gradio-container .prose li,
            .gradio-container .prose strong,
            .gradio-container .prose em {
                color: var(--cf-text-soft) !important;
            }

            .gradio-container textarea,
            .gradio-container input,
            .gradio-container select,
            .gradio-container .cm-editor,
            .gradio-container .cm-scroller,
            .gradio-container .cm-gutters,
            .gradio-container .cm-activeLine,
            .gradio-container .cm-activeLineGutter,
            .gradio-container .cm-content,
            .gradio-container .cm-line,
            .gradio-container .cm-tooltip,
            .gradio-container .ace_editor,
            .gradio-container .ace_gutter,
            .gradio-container .ace_content,
            .gradio-container .ace_scroller {
                background: #0a0a0a !important;
                color: var(--cf-text) !important;
                border-color: var(--cf-border) !important;
            }

            .gradio-container textarea::placeholder,
            .gradio-container input::placeholder {
                color: var(--cf-text-muted) !important;
            }

            .gradio-container .cm-gutters,
            .gradio-container .ace_gutter {
                color: #777 !important;
            }

            .gradio-container button {
                background: #111111 !important;
                color: var(--cf-text) !important;
                border: 1px solid var(--cf-border) !important;
                box-shadow: none !important;
            }

            .gradio-container button:hover {
                background: #161616 !important;
                border-color: var(--cf-border-strong) !important;
            }

            .gradio-container button.primary,
            .gradio-container button[class*="primary"] {
                background: #101010 !important;
                border: 1px solid rgba(126, 182, 255, 0.25) !important;
                box-shadow: inset 0 0 0 1px rgba(126, 182, 255, 0.08) !important;
            }

            .gradio-container button.primary:hover,
            .gradio-container button[class*="primary"]:hover {
                background: #141414 !important;
                border-color: rgba(126, 182, 255, 0.40) !important;
            }

            .gradio-container .tab-nav {
                background: #070707 !important;
                border: 1px solid var(--cf-border) !important;
                border-radius: 16px !important;
                padding: 6px !important;
            }

            .gradio-container .tab-nav button {
                border-radius: 12px !important;
                background: transparent !important;
                border: 1px solid transparent !important;
            }

            .gradio-container .tab-nav button.selected {
                background: #121212 !important;
                border-color: var(--cf-border-strong) !important;
            }

            .gradio-container .label-wrap,
            .gradio-container .label-wrap span,
            .gradio-container .message,
            .gradio-container .caption,
            .gradio-container .hint {
                color: var(--cf-text-soft) !important;
            }

            .gradio-container .gr-accordion summary,
            .gradio-container .gr-accordion summary * {
                color: var(--cf-text) !important;
            }

            .gradio-container pre,
            .gradio-container code {
                background: #090909 !important;
                color: #ededed !important;
            }

            .top-shell {
                margin-bottom: 12px;
                padding: 22px 20px 16px 20px;
                border-radius: 20px;
                background: linear-gradient(180deg, #0c0c0c, #070707);
                border: 1px solid var(--cf-border);
                box-shadow: var(--cf-shadow);
                text-align: center;
            }

            .top-shell h1 {
                margin: 0 0 12px 0;
                font-size: 46px;
                font-weight: 900;
                letter-spacing: -0.04em;
                line-height: 1.05;
                text-align: center;
                color: #7cc7ff;
                text-shadow: 0 0 20px rgba(124, 199, 255, 0.18);
            }

            .top-shell p {
                margin: 0 0 8px 0;
                line-height: 1.6;
                color: var(--cf-text-soft);
                text-align: center;
            }

            .top-shell-strip {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-bottom: 14px;
                justify-content: center;
            }

            .top-shell-pill,
            .playground-chip {
                display: inline-flex;
                align-items: center;
                padding: 8px 12px;
                border-radius: 999px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.06em;
                text-transform: uppercase;
                background: #101010;
                color: #dddddd;
                border: 1px solid var(--cf-border);
            }

            .playground-hero {
                margin-bottom: 10px;
                padding: 18px 18px 10px 18px;
                border-radius: 20px;
                background: linear-gradient(180deg, #0c0c0c, #080808);
                border: 1px solid var(--cf-border);
                box-shadow: var(--cf-shadow);
            }

            .playground-hero h2 {
                margin: 0 0 8px 0;
                font-size: 28px;
                letter-spacing: -0.03em;
                color: #ffffff;
            }

            .playground-hero p {
                margin: 0 0 10px 0;
                color: var(--cf-text-soft);
                line-height: 1.6;
                max-width: 920px;
            }

            .playground-chip-row {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
                margin-bottom: 10px;
            }

            #simulation-drawer {
                position: fixed !important;
                top: 62px;
                right: 0;
                width: min(500px, 96vw);
                height: calc(100vh - 74px);
                overflow-y: auto !important;
                z-index: 999;
                padding: 16px !important;
                box-shadow: -20px 0 50px rgba(0, 0, 0, 0.65);
                border-left: 1px solid rgba(255, 255, 255, 0.08);
                background: rgba(5, 5, 5, 0.98);
                backdrop-filter: blur(10px);
                animation: simDrawerIn 0.34s cubic-bezier(0.22, 1, 0.36, 1);
                will-change: transform, opacity;
            }

            #simulation-drawer .block {
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
                padding: 0 !important;
            }

            .sim-open-btn button {
                background: #0f0f0f !important;
                color: #f4f4f4 !important;
                border: 1px solid rgba(126, 182, 255, 0.28) !important;
                box-shadow: inset 0 0 0 1px rgba(126, 182, 255, 0.08) !important;
            }

            .sim-open-btn button:hover {
                background: #141414 !important;
                border-color: rgba(126, 182, 255, 0.42) !important;
            }

            .sim-close-btn button {
                width: 100%;
                background: #111111 !important;
                color: #e9e9e9 !important;
                border: 1px solid var(--cf-border) !important;
            }

            .sim-shell {
                color: var(--cf-text);
                font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                padding-bottom: 18px;
            }

            .sim-shell-header {
                position: sticky;
                top: 0;
                z-index: 3;
                display: flex;
                align-items: flex-start;
                justify-content: space-between;
                gap: 12px;
                margin: -2px 0 12px 0;
                padding: 16px;
                border-radius: 18px;
                background: linear-gradient(180deg, #101010, #0a0a0a);
                border: 1px solid var(--cf-border);
                box-shadow: 0 12px 28px rgba(0, 0, 0, 0.38);
            }

            .sim-shell-title {
                font-size: 20px;
                font-weight: 800;
                margin-bottom: 4px;
                color: #ffffff;
            }

            .sim-shell-subtitle {
                font-size: 13px;
                line-height: 1.55;
                color: var(--cf-text-soft);
                max-width: 320px;
            }

            .sim-thinking-row {
                display: flex;
                align-items: center;
                gap: 10px;
                margin: 0 0 16px 0;
                padding: 12px 14px;
                border-radius: 16px;
                background: linear-gradient(180deg, #0e0e0e, #090909);
                border: 1px solid rgba(126, 182, 255, 0.14);
                box-shadow: inset 0 0 0 1px rgba(126, 182, 255, 0.03);
            }

            .sim-thinking-row-waiting {
                margin-top: 2px;
            }

            .sim-thinking-pulse {
                width: 10px;
                height: 10px;
                border-radius: 999px;
                background: #8ab8ff;
                box-shadow: 0 0 0 0 rgba(138, 184, 255, 0.45);
                animation: simPulse 1.8s infinite;
                flex: 0 0 auto;
            }

            .sim-thinking-copy {
                font-size: 12px;
                color: #d9e8ff;
                letter-spacing: 0.01em;
            }

            .sim-thinking-dots {
                display: inline-flex;
                align-items: center;
                gap: 5px;
                margin-left: auto;
            }

            .sim-thinking-dots span {
                width: 6px;
                height: 6px;
                border-radius: 999px;
                background: rgba(138, 184, 255, 0.9);
                animation: simDotBounce 1.15s infinite ease-in-out;
            }

            .sim-thinking-dots span:nth-child(2) {
                animation-delay: 0.15s;
            }

            .sim-thinking-dots span:nth-child(3) {
                animation-delay: 0.3s;
            }

            .sim-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: 8px 12px;
                border-radius: 999px;
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.06em;
                white-space: nowrap;
                background: #111111;
            }

            .sim-badge-running {
                color: #d4e8ff;
                border: 1px solid rgba(126, 182, 255, 0.30);
                box-shadow: 0 0 0 1px rgba(126, 182, 255, 0.06), 0 0 20px rgba(126, 182, 255, 0.10);
            }

            .sim-badge-success {
                color: #cbf7df;
                border: 1px solid rgba(125, 226, 180, 0.28);
            }

            .sim-badge-error {
                color: #ffd0d0;
                border: 1px solid rgba(255, 140, 140, 0.28);
            }

            .sim-meta-strip {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: 10px;
                margin-bottom: 16px;
            }

            .sim-meta-pill,
            .sim-phase-card,
            .sim-step-card,
            .sim-stop-card,
            .sim-result-card,
            .sim-empty-state {
                background: linear-gradient(180deg, #101010, #0b0b0b);
                border: 1px solid var(--cf-border);
                box-shadow: none;
            }

            .sim-meta-pill {
                padding: 12px 14px;
                border-radius: 16px;
            }

            .sim-meta-pill span {
                display: block;
                font-size: 11px;
                letter-spacing: 0.05em;
                text-transform: uppercase;
                color: var(--cf-text-muted);
                margin-bottom: 6px;
            }

            .sim-meta-pill strong {
                font-size: 15px;
                color: #ffffff;
            }

            .sim-phase-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 10px;
                margin-bottom: 18px;
            }

            .sim-phase-card {
                padding: 14px;
                border-radius: 16px;
            }

            .sim-phase-title {
                font-size: 13px;
                font-weight: 800;
                margin-bottom: 6px;
                color: #ffffff;
            }

            .sim-phase-desc {
                font-size: 12px;
                line-height: 1.5;
                color: var(--cf-text-soft);
            }

            .sim-phase-done {
                border-color: rgba(255, 255, 255, 0.10);
            }

            .sim-phase-current {
                border-color: rgba(126, 182, 255, 0.35);
                box-shadow: inset 0 0 0 1px rgba(126, 182, 255, 0.10);
            }

            .sim-phase-success {
                border-color: rgba(125, 226, 180, 0.22);
            }

            .sim-phase-error {
                border-color: rgba(255, 140, 140, 0.22);
            }

            .sim-section-title {
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 0.08em;
                text-transform: uppercase;
                color: #d7d7d7;
                margin: 18px 0 10px 0;
            }

            .sim-step-card,
            .sim-stop-card,
            .sim-result-card,
            .sim-empty-state {
                margin-bottom: 12px;
                padding: 14px;
                border-radius: 18px;
            }

            .sim-step-card {
                border-left: 3px solid rgba(126, 182, 255, 0.46);
                transition: transform 0.22s ease, border-color 0.22s ease, box-shadow 0.22s ease, background 0.22s ease;
            }

            .sim-step-card:hover {
                transform: translateY(-1px);
                border-left-color: rgba(126, 182, 255, 0.72);
            }

            .sim-step-active {
                box-shadow: 0 0 0 1px rgba(126, 182, 255, 0.10), 0 0 22px rgba(126, 182, 255, 0.10), inset 0 0 0 1px rgba(126, 182, 255, 0.05);
                animation: simActiveGlow 1.9s ease-in-out infinite;
            }

            .sim-step-error {
                border-left-color: rgba(255, 140, 140, 0.88);
                background: linear-gradient(180deg, #160c0c, #0b0b0b);
            }

            .sim-step-success {
                border-left-color: rgba(125, 226, 180, 0.84);
            }

            .sim-step-top {
                display: flex;
                justify-content: space-between;
                gap: 10px;
                align-items: center;
                margin-bottom: 10px;
            }

            .sim-step-line {
                font-size: 14px;
                font-weight: 800;
                color: #ffffff;
            }

            .sim-step-state {
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.08em;
                color: #d8d8d8;
                background: #101010;
                border: 1px solid var(--cf-border);
                padding: 6px 10px;
                border-radius: 999px;
            }

            .sim-code-block,
            .sim-terminal-block {
                margin: 0 0 10px 0;
                padding: 12px;
                border-radius: 14px;
                overflow-x: auto;
                background: #060606 !important;
                border: 1px solid rgba(255, 255, 255, 0.08);
                color: #efefef;
                font-size: 12px;
                line-height: 1.6;
            }

            .sim-step-reason,
            .sim-result-copy,
            .sim-stop-desc {
                color: var(--cf-text-soft);
                font-size: 13px;
                line-height: 1.6;
            }

            .sim-stop-title,
            .sim-result-title {
                font-size: 14px;
                font-weight: 800;
                color: #ffffff;
                margin-bottom: 8px;
            }

            .sim-result-success {
                border-left: 3px solid rgba(125, 226, 180, 0.84);
            }

            .sim-result-error,
            .sim-stop-card {
                border-left: 3px solid rgba(255, 140, 140, 0.84);
            }

            .sim-result-neutral {
                border-left: 3px solid rgba(126, 182, 255, 0.50);
            }


            @keyframes simDrawerIn {
                0% {
                    opacity: 0;
                    transform: translateX(26px);
                }
                100% {
                    opacity: 1;
                    transform: translateX(0);
                }
            }

            @keyframes simPulse {
                0% {
                    box-shadow: 0 0 0 0 rgba(138, 184, 255, 0.42);
                    opacity: 0.95;
                }
                70% {
                    box-shadow: 0 0 0 10px rgba(138, 184, 255, 0);
                    opacity: 1;
                }
                100% {
                    box-shadow: 0 0 0 0 rgba(138, 184, 255, 0);
                    opacity: 0.95;
                }
            }

            @keyframes simDotBounce {
                0%, 80%, 100% {
                    transform: translateY(0);
                    opacity: 0.35;
                }
                40% {
                    transform: translateY(-3px);
                    opacity: 1;
                }
            }

            @keyframes simActiveGlow {
                0%, 100% {
                    box-shadow: 0 0 0 1px rgba(126, 182, 255, 0.10), 0 0 18px rgba(126, 182, 255, 0.08), inset 0 0 0 1px rgba(126, 182, 255, 0.04);
                }
                50% {
                    box-shadow: 0 0 0 1px rgba(126, 182, 255, 0.16), 0 0 26px rgba(126, 182, 255, 0.16), inset 0 0 0 1px rgba(126, 182, 255, 0.08);
                }
            }
            .gradio-container ::-webkit-scrollbar {
                width: 10px;
                height: 10px;
            }

            .gradio-container ::-webkit-scrollbar-track {
                background: #060606;
            }

            .gradio-container ::-webkit-scrollbar-thumb {
                background: #232323;
                border-radius: 999px;
                border: 2px solid #060606;
            }

            .gradio-container ::-webkit-scrollbar-thumb:hover {
                background: #323232;
            }

            @media (max-width: 1080px) {
                #simulation-drawer {
                    width: min(100vw, 560px);
                }
            }

            @media (max-width: 760px) {
                #simulation-drawer {
                    top: 0;
                    width: 100vw;
                    height: 100vh;
                    border-left: none;
                }

                .sim-meta-strip,
                .sim-phase-grid {
                    grid-template-columns: 1fr;
                }
            }
        </style>

        <div class="top-shell">
            <div class="top-shell-strip">
                <span class="top-shell-pill">AI Coding Arena</span>
                <span class="top-shell-pill">Execution Trace</span>
                <span class="top-shell-pill">Judge-Ready UI</span>
            </div>
            <h1>CodeFix Arena</h1>
            <p>Debug, refactor, and inspect execution in a dark AI coding workspace designed for guided challenges and free-form playground testing.</p>
            <p style="margin-top: 0; color: #8b8b8b;">Use <b style="color:#ffffff;">Arena</b> for structured challenge solving and <b style="color:#ffffff;">Playground</b> for live execution tracing without disturbing the validated backend pipeline.</p>
        </div>
        """)

        with gr.Tabs():
            with gr.Tab("Arena"):
                gr.Markdown("## Challenge Workspace")

                with gr.Row():
                    with gr.Column(scale=3):
                        task_selector = gr.Dropdown(
                            choices=[
                                ("Task 1 - Debug (Easy)", 1),
                                ("Task 2 - Refactor (Medium)", 2),
                                ("Task 3 - Java Refactor (Hard)", 3),
                            ],
                            label="Choose Challenge",
                            value=1,
                        )
                    with gr.Column(scale=1):
                        load_button = gr.Button("Load Challenge", variant="primary")
                    with gr.Column(scale=1):
                        auto_fix_button = gr.Button("Apply Suggested Fix")

                with gr.Row():
                    task_info_box = gr.Textbox(label="Challenge Details", lines=6)
                    status_box = gr.Textbox(label="Workspace Status", lines=6)
                    verdict_box = gr.Textbox(label="Result Summary", lines=6)

                gr.Markdown("### Project Workspace")

                with gr.Row():
                    with gr.Column(scale=1):
                        file_list_box = gr.Textbox(label="Project Files", lines=12)
                        list_files_button = gr.Button("Refresh Files")
                        file_path_input = gr.Textbox(label="Current File", placeholder="main.py")

                        with gr.Row():
                            read_file_button = gr.Button("Open File")
                            write_file_button = gr.Button("Save Changes")

                    with gr.Column(scale=2):
                        file_content_box = gr.Code(label="Editor", language="python", lines=24)

                gr.Markdown("### Run and Inspect")

                with gr.Row():
                    command_input = gr.Textbox(
                        label="Command",
                        placeholder="python3 main.py"
                    )
                    run_button = gr.Button("Run in Workspace", variant="primary")

                with gr.Row():
                    stdout_box = gr.Textbox(label="Output", lines=8)
                    stderr_box = gr.Textbox(label="Errors / Warnings", lines=8)

                gr.Markdown("### Evaluation")

                with gr.Row():
                    reward_box = gr.Textbox(label="Reward", lines=1)
                    feedback_box = gr.Textbox(label="Feedback", lines=4)

                score_breakdown_box = gr.JSON(label="Score Breakdown")

                with gr.Accordion("Agent Insights", open=True):
                    agent_trace_box = gr.Textbox(label="Action Trace", lines=10)
                    thinking_box = gr.Markdown(label="Thinking Viewer")

                with gr.Accordion("Debug Assistant", open=False):
                    gr.Markdown(
                        """
Ask natural questions like:
- what is wrong here?
- how should I fix this?
- explain the error
- what should I do next?
"""
                    )
                    user_message_box = gr.Textbox(
                        label="Your Question",
                        placeholder="For example: what is wrong here?"
                    )
                    assistant_button = gr.Button("Ask Assistant")
                    assistant_reply_box = gr.Markdown(label="Assistant Reply")

                load_button.click(
                    fn=load_task_console,
                    inputs=[task_selector],
                    outputs=[
                        task_info_box,
                        file_list_box,
                        file_path_input,
                        file_content_box,
                        command_input,
                        status_box,
                        stdout_box,
                        stderr_box,
                        reward_box,
                        feedback_box,
                        score_breakdown_box,
                        agent_trace_box,
                        verdict_box,
                        thinking_box,
                    ],
                )

                list_files_button.click(
                    fn=list_files_console,
                    inputs=[],
                    outputs=[file_list_box, status_box, agent_trace_box, thinking_box],
                )

                read_file_button.click(
                    fn=read_file_console,
                    inputs=[file_path_input],
                    outputs=[file_content_box, status_box, agent_trace_box, thinking_box],
                )

                write_file_button.click(
                    fn=write_file_console,
                    inputs=[file_path_input, file_content_box],
                    outputs=[status_box, score_breakdown_box, agent_trace_box, verdict_box, thinking_box],
                )

                run_button.click(
                    fn=run_command_console,
                    inputs=[command_input],
                    outputs=[
                        stdout_box,
                        stderr_box,
                        reward_box,
                        feedback_box,
                        status_box,
                        score_breakdown_box,
                        agent_trace_box,
                        verdict_box,
                        thinking_box,
                    ],
                )

                assistant_button.click(
                    fn=ask_assistant_console,
                    inputs=[task_selector, file_content_box, user_message_box],
                    outputs=[assistant_reply_box],
                )

                auto_fix_button.click(
                    fn=auto_fix_console,
                    inputs=[task_selector, file_path_input],
                    outputs=[file_content_box, status_box, score_breakdown_box, agent_trace_box, verdict_box, thinking_box],
                )

            with gr.Tab("Playground"):
                gr.HTML(
                    """
                    <div class="playground-hero">
                        <div class="playground-chip-row">
                            <span class="playground-chip">Execution Intelligence</span>
                            <span class="playground-chip">Live Trace</span>
                            <span class="playground-chip">Judge-Friendly Demo</span>
                        </div>
                        <h2>Playground</h2>
                        <p>Paste code, import a source file, run fast analysis, and open a plain-black execution panel that simulates how the program likely moved through its logic.</p>
                    </div>
                    """
                )

                with gr.Row():
                    playground_language = gr.Dropdown(
                        choices=["python", "java", "cpp"],
                        value="python",
                        label="Language",
                    )

                    playground_file = gr.File(
                        label="Upload Source File",
                        file_types=[".py", ".java", ".cpp", ".cc", ".cxx", ".c", ".txt"],
                        type="filepath",
                    )

                    import_file_button = gr.Button("Import File", variant="secondary")

                playground_code = gr.Code(
                    label="Playground Editor",
                    language="python",
                    lines=24,
                )

                with gr.Row():
                    analyze_button = gr.Button("Run Analysis", variant="primary")
                    simulate_button = gr.Button("Open Live Trace", elem_classes=["sim-open-btn"])

                with gr.Row():
                    playground_summary = gr.Textbox(label="Summary / Import Status", lines=6)
                    playground_stdout = gr.Textbox(label="Output", lines=8)
                    playground_stderr = gr.Textbox(label="Errors / Warnings", lines=8)

                with gr.Column(visible=False, elem_id="simulation-drawer") as simulation_drawer:
                    close_sim_button = gr.Button("Hide Execution Panel", elem_classes=["sim-close-btn"])
                    simulation_output = gr.HTML(build_simulation_trace("python", "", "", ""))

                import_file_button.click(
                    fn=import_playground_file,
                    inputs=[playground_file],
                    outputs=[playground_language, playground_code, playground_summary],
                )

                analyze_button.click(
                    fn=run_playground,
                    inputs=[playground_language, playground_code],
                    outputs=[playground_summary, playground_stdout, playground_stderr],
                )

                simulate_button.click(
                    fn=run_playground_simulation,
                    inputs=[playground_language, playground_code],
                    outputs=[
                        playground_summary,
                        playground_stdout,
                        playground_stderr,
                        simulation_drawer,
                        simulation_output,
                    ],
                )

                close_sim_button.click(
                    fn=close_simulation_drawer,
                    inputs=[],
                    outputs=[simulation_drawer],
                )

    return demo


base_app = FastAPI(title="CodeFix Arena OpenEnv Server")


@base_app.post("/reset", response_model=StepResponseModel)
def reset_endpoint(payload: Optional[ResetRequest] = Body(default=None)):
    try:
        task_id = payload.task_id if payload else None

        if task_id is None:
            state = env.reset()
        else:
            state = env.reset(task_id=int(task_id))

        snapshot_state(state)

        return StepResponseModel(
            observation=build_observation_model(state),
            reward=0.01,
            done=False,
            info={"message": "Environment reset successful."},
        )
    except Exception as e:
        fallback_state = snapshot_state()
        return StepResponseModel(
            observation=build_observation_model(fallback_state),
            reward=0.01,
            done=False,
            info={"message": f"Reset failed: {str(e)}"},
        )


@base_app.post("/step", response_model=StepResponseModel)
def step_endpoint(action: ActionRequest):
    try:
        action_payload = model_to_dict(action)
        state, reward, done, info = env.step(action_payload)
        snapshot_state(state)

        safe_info = sanitize_info_payload(info)

        return StepResponseModel(
            observation=build_observation_model(state),
            reward=safe_reward(reward),
            done=bool(done),
            info=safe_info,
        )

    except Exception as e:
        fallback_state = snapshot_state()
        return StepResponseModel(
            observation=build_observation_model(fallback_state),
            reward=0.01,
            done=False,
            info={"message": f"Step failed: {str(e)}"},
        )


@base_app.get("/state", response_model=ObservationModel)
def state_endpoint():
    current_state = snapshot_state()
    return build_observation_model(current_state)


demo = create_demo()
app = gr.mount_gradio_app(base_app, demo, path="/")


def main():
    import uvicorn
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run("app:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    port = int(os.getenv("PORT", "7860"))
    uvicorn.run(app, host="0.0.0.0", port=port)

