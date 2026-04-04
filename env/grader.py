class CodingTaskGrader:
    @staticmethod
    def grade(task, workspace, last_command_result):
        reward = 0.0
        feedback_parts = []

        # 🧠 Multi-metric scoring structure
        score_breakdown = {
            "execution": 0.0,
            "correctness": 0.0,
            "structure": 0.0,
            "efficiency": 0.0,
            "robustness": 0.0,
            "penalties": 0.0,
            "task_type": task.get("type", "unknown"),
            "expected_fix": task.get("expected_fix", "unknown"),
        }

        task_type = task.get("type")
        expected_fix = task.get("expected_fix")

        stdout = (last_command_result.get("stdout") or "").strip()
        stderr = (last_command_result.get("stderr") or "").strip()
        status = last_command_result.get("status", "error")

        # =============================
        # 🧠 EXECUTION SCORE
        # =============================
        if status == "success":
            score_breakdown["execution"] = 0.3
            reward += 0.3
            feedback_parts.append("Execution successful.")
        else:
            score_breakdown["execution"] = 0.0
            feedback_parts.append("Execution failed.")

        # =============================
        # 🧠 TASK-SPECIFIC GRADING
        # =============================
        try:
            if task_type == "debug":
                r, details, msgs = CodingTaskGrader._grade_python_debug(workspace, stdout)
            elif task_type == "refactor" and expected_fix == "refactor_repeated_logic":
                r, details, msgs = CodingTaskGrader._grade_python_refactor(workspace, stdout)
            elif task_type == "refactor" and expected_fix == "java_multifile_refactor_fix":
                r, details, msgs = CodingTaskGrader._grade_java_multifile(workspace, stdout)
            else:
                r, details, msgs = 0.0, {}, ["Unknown task type"]

            reward += r
            score_breakdown.update(details)
            feedback_parts.extend(msgs)

        except Exception as e:
            feedback_parts.append(f"Grader error: {e}")
            score_breakdown["grader_error"] = str(e)

        # =============================
        # 🧠 PENALTY SYSTEM (NEW 🔥)
        # =============================
        penalties = 0.0

        if "infinite" in stderr.lower():
            penalties -= 0.1
            feedback_parts.append("Penalty: possible infinite loop detected.")

        if len(stdout) > 500:
            penalties -= 0.05
            feedback_parts.append("Penalty: excessive output.")

        score_breakdown["penalties"] = penalties
        reward += penalties

        # =============================
        # 🧠 FINAL NORMALIZATION
        # =============================
        reward = max(0.0, min(round(reward, 3), 1.0))

        if reward >= 0.9:
            score_breakdown["overall"] = "excellent"
        elif reward >= 0.7:
            score_breakdown["overall"] = "good"
        elif reward > 0.0:
            score_breakdown["overall"] = "partial"
        else:
            score_breakdown["overall"] = "failed"

        return {
            "reward": reward,
            "feedback": " | ".join(feedback_parts),
            "score_breakdown": score_breakdown,
        }

    # =============================
    # 🔍 DEBUG TASK
    # =============================
    @staticmethod
    def _grade_python_debug(workspace, stdout):
        reward = 0.0
        details = {}
        messages = []

        content = workspace.read_file("main.py")

        # Structure
        if "def add(" in content and "):" in content:
            reward += 0.15
            details["structure"] = 0.15
            messages.append("Function syntax corrected.")

        # Correctness
        if "return a + b" in content or "return a+b" in content:
            reward += 0.15
            details["correctness"] = 0.15
            messages.append("Correct logic detected.")

        # Hidden test
        hidden = workspace.run_command(
            "py -c \"from main import add; print(add(10, 5))\""
        )

        if hidden.get("status") == "success" and "15" in hidden.get("stdout", ""):
            reward += 0.25
            details["robustness"] = 0.25
            messages.append("Hidden test passed.")

        # Output check
        if stdout == "5":
            reward += 0.15
            details["execution_output"] = 0.15
            messages.append("Expected output correct.")

        return reward, details, messages

    # =============================
    # 🔍 REFACTOR TASK
    # =============================
    @staticmethod
    def _grade_python_refactor(workspace, stdout):
        reward = 0.0
        details = {}
        messages = []

        content = workspace.read_file("app.py")

        if "def calculate_total" in content:
            reward += 0.15
            details["structure"] = 0.15
            messages.append("Helper function created.")

        helper_calls = content.count("calculate_total(")
        if helper_calls >= 3:
            reward += 0.15
            details["efficiency"] = 0.15
            messages.append("Logic reused properly.")

        repeated = content.count("total += 100") + content.count("total += 50")
        if repeated <= 2:
            reward += 0.1
            details["duplication_reduction"] = 0.1
            messages.append("Duplicate logic reduced.")

        hidden = workspace.run_command("py app.py")
        if hidden.get("status") == "success" and hidden.get("stdout", "").count("150") >= 2:
            reward += 0.2
            details["correctness"] = 0.2
            messages.append("Behavior correct.")

        if stdout.count("150") >= 2:
            reward += 0.15
            details["execution_output"] = 0.15
            messages.append("Output verified.")

        return reward, details, messages

    # =============================
    # 🔍 JAVA TASK
    # =============================
    @staticmethod
    def _grade_java_multifile(workspace, stdout):
        reward = 0.0
        details = {}
        messages = []

        service = workspace.read_file("CalculatorService.java")
        formatter = workspace.read_file("ResultFormatter.java")

        if "return a + b;" in service:
            reward += 0.15
            details["correctness"] = 0.15
            messages.append("Logic fixed.")

        if "public static String format(" in formatter:
            reward += 0.15
            details["structure"] = 0.15
            messages.append("Method fixed.")

        if "\"Result = \" + result" in formatter:
            reward += 0.1
            details["output_format"] = 0.1
            messages.append("Formatting correct.")

        hidden = workspace.run_command(
            r'"C:\Program Files\Java\jdk1.8.0_202\bin\javac.exe" Main.java CalculatorService.java ResultFormatter.java && "C:\Program Files\Java\jdk1.8.0_202\bin\java.exe" Main'
        )

        if hidden.get("status") == "success" and "Result = 15" in hidden.get("stdout", ""):
            reward += 0.2
            details["robustness"] = 0.2
            messages.append("Hidden validation passed.")

        if "Result = 15" in stdout:
            reward += 0.15
            details["execution_output"] = 0.15
            messages.append("Final output correct.")

        return reward, details, messages


