import os
import gradio as gr
from env.coding_env import CodingAssistantEnv
from env.runtime_debugger import RuntimeDebugger

env = CodingAssistantEnv()
AGENT_TRACE = []


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
            reward="0.000",
            done=False,
            extra="Workspace initialized and ready for agent interaction."
        )

        score_breakdown = {
            "step": state.get("step", 0),
            "max_steps": state.get("max_steps", 0),
            "files": files,
            "command_prefilled": default_command,
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
            "0.000",
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
            format_status("Task loading failed.", reward="0.000", done=False, extra=str(e)),
            "",
            "",
            "0.000",
            str(e),
            {"error": str(e)},
            build_agent_trace(AGENT_TRACE),
            "Agent Verdict:\n- Task loading failed",
            thinking,
        )


def list_files_console():
    try:
        state, reward, done, info = env.step({"tool": "list_files"})
        files = info.get("tool_result", {}).get("files", [])
        AGENT_TRACE.append("Listed workspace files.")
        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            "\n".join(files),
            format_status("Workspace file list refreshed.", reward=f"{reward:.3f}", done=done),
            build_agent_trace(AGENT_TRACE),
            thinking,
        )
    except Exception as e:
        AGENT_TRACE.append(f"Failed to list files. Error: {e}")
        thinking = build_agent_thinking(AGENT_TRACE)
        return (
            "",
            format_status("Failed to list files.", reward="0.000", done=False, extra=str(e)),
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
        state, reward, done, info = env.step({
            "tool": "read_file",
            "path": path,
        })

        AGENT_TRACE.append(f"Read file: {path}.")
        content = info.get("tool_result", {}).get("content", "")
        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            content,
            format_status("File read successfully.", reward=f"{reward:.3f}", done=done),
            build_agent_trace(AGENT_TRACE),
            thinking,
        )
    except Exception as e:
        AGENT_TRACE.append(f"Failed to read file: {path}. Error: {e}")
        thinking = build_agent_thinking(AGENT_TRACE)
        return (
            "",
            format_status("File read failed.", reward="0.000", done=False, extra=str(e)),
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
        state, reward, done, info = env.step({
            "tool": "write_file",
            "path": path,
            "content": content or "",
        })

        AGENT_TRACE.append(f"Wrote updated content to {path}.")

        tool_message = info.get("tool_result", {}).get("message", "Write completed.")
        score_breakdown = {
            "step": state.get("step", 0),
            "max_steps": state.get("max_steps", 0),
            "last_action": "write_file",
            "path": path,
        }

        verdict = (
            "Agent Verdict:\n"
            f"- File updated: {path}\n"
            f"- Reward impact: {reward:.3f}\n"
            f"- Episode done: {done}"
        )

        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            format_status(tool_message, reward=f"{reward:.3f}", done=done),
            score_breakdown,
            build_agent_trace(AGENT_TRACE),
            verdict,
            thinking,
        )
    except Exception as e:
        AGENT_TRACE.append(f"Failed to write file: {path}. Error: {e}")
        thinking = build_agent_thinking(AGENT_TRACE)
        return (
            format_status("Write failed.", reward="0.000", done=False, extra=str(e)),
            {"error": str(e)},
            build_agent_trace(AGENT_TRACE),
            "Agent Verdict:\n- File write failed",
            thinking,
        )


def run_command_console(command):
    command = (command or "").strip()
    if not command:
        return (
            "",
            "",
            "0.000",
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

        result = info.get("tool_result", {})
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        feedback = info.get("feedback", "")

        AGENT_TRACE.append(f"Ran command: {command}.")
        AGENT_TRACE.append(f"Command status: {result.get('status', 'unknown')}.")

        status = format_status(
            f"Command status: {result.get('status', 'unknown')}",
            reward=f"{reward:.3f}",
            done=done,
            extra=f"Expected Fix: {info.get('expected_fix', 'N/A')}",
        )

        score_breakdown = info.get("score_breakdown", {})
        if not score_breakdown:
            score_breakdown = {
                "step": state.get("step", 0),
                "max_steps": state.get("max_steps", 0),
                "last_action": "run_command",
                "command": command,
                "command_status": result.get("status", "unknown"),
                "reward": round(reward, 3),
            }

        verdict = (
            "Agent Verdict:\n"
            f"- Execution: {result.get('status', 'unknown')}\n"
            f"- Reward: {reward:.3f}\n"
            f"- Feedback: {feedback if feedback else 'No feedback'}"
        )

        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            stdout,
            stderr,
            f"{reward:.3f}",
            feedback,
            status,
            score_breakdown,
            build_agent_trace(AGENT_TRACE),
            verdict,
            thinking,
        )
    except Exception as e:
        AGENT_TRACE.append(f"Command run failed: {command}. Error: {e}")
        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            "",
            str(e),
            "0.000",
            "Command execution failed.",
            format_status("Command failed.", reward="0.000", done=False, extra=str(e)),
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
        state, reward, done, info = env.step({
            "tool": "write_file",
            "path": current_path,
            "content": fixed_code,
        })

        AGENT_TRACE.append(f"Auto-fix applied to {current_path}.")

        score_breakdown = {
            "step": state.get("step", 0),
            "max_steps": state.get("max_steps", 0),
            "last_action": "auto_fix_write",
            "path": current_path,
        }

        verdict = (
            "Agent Verdict:\n"
            "- Suggested fix generated\n"
            f"- File updated: {current_path}\n"
            f"- Reward impact: {reward:.3f}\n"
            f"- Episode done: {done}"
        )

        thinking = build_agent_thinking(AGENT_TRACE)

        return (
            fixed_code,
            f"Auto-fix applied.\nReward: {reward:.3f}\nDone: {done}",
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


def run_playground(language, code):
    result = RuntimeDebugger.analyze_code(language, code)

    summary = (
        f"Status: {result['status']}\n"
        f"Message: {result['message']}\n"
        f"Hint: {result['hint']}"
    )

    return summary, result["stdout"], result["stderr"]


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


with gr.Blocks(title="CodeFix Arena") as demo:
    gr.HTML("""
    <div style="padding: 14px 6px 4px 6px;">
        <h1 style="margin-bottom: 8px;">🚀 CodeFix Arena</h1>
        <p style="font-size: 17px; margin-bottom: 8px;">
            Debug. Refactor. Improve. Work with code like a real developer.
        </p>
        <p style="margin-top: 0; color: #666;">
            Use <b>Arena</b> for guided coding challenges with evaluation and reasoning traces,
            or switch to <b>Playground</b> to test your own files freely.
        </p>
    </div>
    """)

    with gr.Tabs():
        with gr.Tab("Arena"):
            gr.Markdown("## 🧩 Guided Challenge Workspace")

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

            gr.Markdown("### 📁 Project Workspace")

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

            gr.Markdown("### ⚡ Run and Inspect")

            with gr.Row():
                command_input = gr.Textbox(
                    label="Command",
                    placeholder="python3 main.py"
                )
                run_button = gr.Button("Run in Workspace", variant="primary")

            with gr.Row():
                stdout_box = gr.Textbox(label="Output", lines=8)
                stderr_box = gr.Textbox(label="Errors / Warnings", lines=8)

            gr.Markdown("### 📊 Evaluation")

            with gr.Row():
                reward_box = gr.Textbox(label="Reward", lines=1)
                feedback_box = gr.Textbox(label="Feedback", lines=4)

            score_breakdown_box = gr.JSON(label="Score Breakdown")

            with gr.Accordion("🧠 Agent Insights", open=True):
                agent_trace_box = gr.Textbox(label="Action Trace", lines=10)
                thinking_box = gr.Markdown(label="Thinking Viewer")

            with gr.Accordion("💡 Debug Assistant", open=False):
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
            gr.Markdown(
                """
## 🧪 Free Playground

Test your own code here:
- paste code directly
- upload a source file
- switch language manually
- run quick analysis without using the challenge flow
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

            analyze_button = gr.Button("Run Analysis", variant="primary")

            with gr.Row():
                playground_summary = gr.Textbox(label="Summary / Import Status", lines=6)
                playground_stdout = gr.Textbox(label="Output", lines=8)
                playground_stderr = gr.Textbox(label="Errors / Warnings", lines=8)

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

demo.launch(server_name="0.0.0.0", server_port=7860)



