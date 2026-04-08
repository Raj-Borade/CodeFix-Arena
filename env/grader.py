import os
import shutil
import sys

EPS = 0.01
MAX_SCORE = 0.95


class CodingTaskGrader:
    @staticmethod
    def clamp(score: float) -> float:
        try:
            score = float(score)
        except Exception:
            return EPS

        if score >= 1.0:
            return MAX_SCORE
        if score <= 0.0:
            return EPS
        return score

    @staticmethod
    def safe_component(value) -> float:
        try:
            value = float(value)
        except Exception:
            return EPS

        if value >= 1.0:
            return MAX_SCORE
        if value <= 0.0:
            return EPS
        return value

    @staticmethod
    def add_score(details: dict, key: str, value: float):
        details[key] = CodingTaskGrader.safe_component(value)

    @staticmethod
    def safe_text(value) -> str:
        return str(value or "").strip()

    @staticmethod
    def read_if_exists(workspace, filename: str) -> str:
        try:
            return workspace.read_file(filename)
        except Exception:
            return ""

    @staticmethod
    def command_success(result: dict) -> bool:
        return str(result.get("status", "")).strip().lower() == "success"

    @staticmethod
    def find_java_tools():
        java_home = os.environ.get("JAVA_HOME", "").strip()
        javac = shutil.which("javac")
        java = shutil.which("java")

        if not javac and java_home:
            candidate = os.path.join(
                java_home, "bin", "javac.exe" if os.name == "nt" else "javac"
            )
            if os.path.exists(candidate):
                javac = candidate

        if not java and java_home:
            candidate = os.path.join(
                java_home, "bin", "java.exe" if os.name == "nt" else "java"
            )
            if os.path.exists(candidate):
                java = candidate

        return javac, java

    @staticmethod
    def grade(task, workspace, last_command_result):
        reward = EPS
        feedback_parts = []

        score_breakdown = {
            "execution": EPS,
            "correctness": EPS,
            "structure": EPS,
            "efficiency": EPS,
            "robustness": EPS,
            "penalties": EPS,
            "task_type": task.get("type", "unknown"),
            "expected_fix": task.get("expected_fix", "unknown"),
        }

        task_type = task.get("type")
        expected_fix = task.get("expected_fix")
        difficulty = str(task.get("difficulty", "medium")).strip().lower()

        stdout = CodingTaskGrader.safe_text(last_command_result.get("stdout"))
        stderr = CodingTaskGrader.safe_text(last_command_result.get("stderr"))
        status = CodingTaskGrader.safe_text(last_command_result.get("status")).lower()
        python_exe = sys.executable or "python"

        if status == "success":
            reward += 0.28
            score_breakdown["execution"] = CodingTaskGrader.safe_component(0.28)
            feedback_parts.append("Execution successful.")
        else:
            reward += 0.04
            score_breakdown["execution"] = CodingTaskGrader.safe_component(0.04)
            feedback_parts.append("Execution failed (partial credit given).")

        try:
            if task_type == "debug":
                r, details, msgs = CodingTaskGrader._grade_python_debug(
                    workspace, stdout, python_exe
                )
            elif task_type == "refactor" and expected_fix == "refactor_repeated_logic":
                r, details, msgs = CodingTaskGrader._grade_python_refactor(
                    workspace, stdout, python_exe
                )
            elif task_type == "refactor" and expected_fix == "java_multifile_refactor_fix":
                r, details, msgs = CodingTaskGrader._grade_java_multifile(
                    workspace, stdout
                )
            else:
                r, details, msgs = CodingTaskGrader._grade_fallback(
                    workspace, task, stdout
                )

            reward += float(r)

            for k, v in details.items():
                if isinstance(v, (int, float)):
                    score_breakdown[k] = CodingTaskGrader.safe_component(v)
                else:
                    score_breakdown[k] = v

            feedback_parts.extend(msgs)

        except Exception as e:
            feedback_parts.append(f"Grader error: {e}")
            score_breakdown["grader_error"] = str(e)

        penalties = EPS

        stderr_lower = stderr.lower()
        if "infinite" in stderr_lower or "recursionerror" in stderr_lower:
            penalties = -0.10
            feedback_parts.append("Penalty: possible infinite loop or runaway recursion detected.")

        if len(stdout) > 1200:
            penalties = min(penalties, -0.05) if penalties < 0 else -0.05
            feedback_parts.append("Penalty: excessive output.")

        if "traceback" in stderr_lower:
            penalties = min(penalties, -0.08) if penalties < 0 else -0.08
            feedback_parts.append("Penalty: traceback detected.")

        if penalties < 0:
            reward += penalties

        reward = max(EPS, reward)
        score_breakdown["penalties"] = CodingTaskGrader.safe_component(
            penalties if penalties > 0 else EPS
        )

        difficulty_bonus = {
            "easy": 0.0,
            "medium": 0.01,
            "hard": 0.02,
        }.get(difficulty, 0.01)

        reward += difficulty_bonus
        score_breakdown["difficulty_bonus"] = CodingTaskGrader.safe_component(
            difficulty_bonus if difficulty_bonus > 0 else EPS
        )

        reward = float(f"{reward:.6f}")
        reward = min(MAX_SCORE, max(EPS, reward))

        if reward >= 0.85:
            score_breakdown["overall"] = "excellent"
        elif reward >= 0.65:
            score_breakdown["overall"] = "good"
        elif reward > EPS:
            score_breakdown["overall"] = "partial"
        else:
            score_breakdown["overall"] = "failed"

        score_breakdown["reward"] = reward

        return {
            "reward": reward,
            "feedback": " | ".join(feedback_parts),
            "score_breakdown": score_breakdown,
        }

    @staticmethod
    def _grade_fallback(workspace, task, stdout):
        reward = 0.05
        details = {}
        messages = ["Fallback grading applied."]

        files = task.get("files") or []
        if files:
            readable = 0
            for f in files:
                if CodingTaskGrader.read_if_exists(workspace, f):
                    readable += 1
            if readable == len(files):
                reward += 0.06
                CodingTaskGrader.add_score(details, "structure", 0.06)
                messages.append("Expected files readable.")

        if stdout:
            reward += 0.05
            CodingTaskGrader.add_score(details, "correctness", 0.05)
            messages.append("Program produced output.")

        return CodingTaskGrader.clamp(reward), details, messages

    @staticmethod
    def _grade_python_debug(workspace, stdout, python_exe):
        reward = EPS
        details = {}
        messages = []

        content = CodingTaskGrader.read_if_exists(workspace, "main.py")

        if "def add(" in content:
            reward += 0.10
            CodingTaskGrader.add_score(details, "structure", 0.10)
            messages.append("Function signature present.")

        if "return a + b" in content or "return a+b" in content:
            reward += 0.18
            CodingTaskGrader.add_score(details, "correctness", 0.18)
            messages.append("Addition logic corrected.")

        if "print(add(2, 3))" in content or "print(add(2,3))" in content:
            reward += 0.05
            CodingTaskGrader.add_score(details, "robustness", 0.05)
            messages.append("Expected call retained.")

        hidden = {"status": "error", "stdout": "", "stderr": ""}
        try:
            hidden = workspace.run_command(
                f"\"{python_exe}\" -c \"from main import add; print(add(10, 5))\""
            )
        except Exception:
            pass

        if CodingTaskGrader.command_success(hidden):
            reward += 0.12
            CodingTaskGrader.add_score(details, "execution_hidden", 0.12)

            hidden_stdout = CodingTaskGrader.safe_text(hidden.get("stdout"))
            if "15" in hidden_stdout:
                reward += 0.14
                CodingTaskGrader.add_score(details, "hidden_correctness", 0.14)
                messages.append("Hidden test passed.")

        if stdout:
            reward += 0.05
            if stdout == "5":
                reward += 0.15
                CodingTaskGrader.add_score(details, "execution_output", 0.15)
                messages.append("Expected output correct.")
            else:
                reward += 0.06
                CodingTaskGrader.add_score(details, "execution_output_partial", 0.06)

        return CodingTaskGrader.clamp(reward), details, messages

    @staticmethod
    def _grade_python_refactor(workspace, stdout, python_exe):
        reward = EPS
        details = {}
        messages = []

        content = CodingTaskGrader.read_if_exists(workspace, "app.py")

        if "def calculate_total" in content:
            reward += 0.12
            CodingTaskGrader.add_score(details, "structure", 0.12)
            messages.append("Helper function created.")

        helper_calls = content.count("calculate_total(")
        if helper_calls >= 3:
            reward += 0.16
            CodingTaskGrader.add_score(details, "efficiency", 0.16)
            messages.append("Logic reused properly.")
        elif helper_calls >= 2:
            reward += 0.12
            CodingTaskGrader.add_score(details, "efficiency_partial", 0.12)
            messages.append("Helper reuse detected.")
        elif helper_calls >= 1:
            reward += 0.06
            CodingTaskGrader.add_score(details, "efficiency_partial", 0.06)

        repeated = content.count("total += 100") + content.count("total += 50")
        if repeated <= 2:
            reward += 0.12
            CodingTaskGrader.add_score(details, "duplication_reduction", 0.12)
            messages.append("Duplicate logic reduced.")
        elif repeated <= 4:
            reward += 0.05
            CodingTaskGrader.add_score(details, "duplication_reduction_partial", 0.05)

        if "process_order()" in content and "process_cart()" in content:
            reward += 0.05
            CodingTaskGrader.add_score(details, "robustness", 0.05)
            messages.append("Entry-point behavior preserved.")

        hidden = {"status": "error", "stdout": "", "stderr": ""}
        try:
            hidden = workspace.run_command(f"\"{python_exe}\" app.py")
        except Exception:
            pass

        if CodingTaskGrader.command_success(hidden):
            reward += 0.10
            CodingTaskGrader.add_score(details, "execution_hidden", 0.10)

            hidden_stdout = CodingTaskGrader.safe_text(hidden.get("stdout"))
            if hidden_stdout.count("150") >= 2:
                reward += 0.14
                CodingTaskGrader.add_score(details, "correctness", 0.14)
                messages.append("Behavior correct.")

        if stdout:
            reward += 0.05
            if stdout.count("150") >= 2:
                reward += 0.14
                CodingTaskGrader.add_score(details, "execution_output", 0.14)
                messages.append("Output verified.")
            else:
                reward += 0.06
                CodingTaskGrader.add_score(details, "execution_output_partial", 0.06)

        return CodingTaskGrader.clamp(reward), details, messages

    @staticmethod
    def _grade_java_multifile(workspace, stdout):
        reward = EPS
        details = {}
        messages = []

        service = CodingTaskGrader.read_if_exists(workspace, "CalculatorService.java")
        formatter = CodingTaskGrader.read_if_exists(workspace, "ResultFormatter.java")
        main_file = CodingTaskGrader.read_if_exists(workspace, "Main.java")

        if "return a + b;" in service:
            reward += 0.14
            CodingTaskGrader.add_score(details, "correctness", 0.14)
            messages.append("Calculator logic fixed.")

        if "public static String format(" in formatter:
            reward += 0.12
            CodingTaskGrader.add_score(details, "structure", 0.12)
            messages.append("Formatter method present.")

        if "\"Result = \" + result" in formatter:
            reward += 0.10
            CodingTaskGrader.add_score(details, "output_format", 0.10)
            messages.append("Output formatting correct.")

        if "CalculatorService" in main_file and "ResultFormatter" in main_file:
            reward += 0.08
            CodingTaskGrader.add_score(details, "integration", 0.08)
            messages.append("Main integrates service and formatter.")

        if ".add(" in main_file:
            reward += 0.06
            CodingTaskGrader.add_score(details, "usage_validation", 0.06)
            messages.append("Addition method is used in main flow.")

        if ".format(" in main_file:
            reward += 0.06
            CodingTaskGrader.add_score(details, "formatter_usage", 0.06)
            messages.append("Formatter is used in main flow.")

        javac, java = CodingTaskGrader.find_java_tools()

        if javac and java:
            hidden = {"status": "error", "stdout": "", "stderr": ""}
            try:
                hidden = workspace.run_command(
                    f"\"{javac}\" Main.java CalculatorService.java ResultFormatter.java && \"{java}\" Main"
                )
            except Exception:
                hidden = {"status": "error", "stdout": "", "stderr": "Java execution call failed."}

            if CodingTaskGrader.command_success(hidden):
                reward += 0.10
                CodingTaskGrader.add_score(details, "execution_hidden", 0.10)

                hidden_stdout = CodingTaskGrader.safe_text(hidden.get("stdout"))
                if "Result = 15" in hidden_stdout:
                    reward += 0.16
                    CodingTaskGrader.add_score(details, "robustness", 0.16)
                    messages.append("Hidden Java validation passed.")
                else:
                    reward += 0.05
                    CodingTaskGrader.add_score(details, "robustness_partial", 0.05)
            else:
                reward += 0.04
                CodingTaskGrader.add_score(details, "execution_partial", 0.04)
                messages.append("Java tools available but execution failed.")
        else:
            reward += 0.06
            CodingTaskGrader.add_score(details, "execution_partial", 0.06)
            messages.append("Java tools missing, static validation credit assigned.")

        if "Result = 15" in stdout:
            reward += 0.14
            CodingTaskGrader.add_score(details, "execution_output", 0.14)
            messages.append("Final output correct.")
        elif stdout:
            reward += 0.05
            CodingTaskGrader.add_score(details, "execution_output_partial", 0.05)

        return CodingTaskGrader.clamp(reward), details, messages
