import os
from typing import Any, Dict, List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _is_windows() -> bool:
    return os.name == "nt"


def _python_cmd(script_name: str) -> str:
    return f"py {script_name}" if _is_windows() else f"python3 {script_name}"


def _java_run_command() -> str:
    """
    Platform-aware Java compile+run command.

    Priority:
    1. JAVA_COMPILE_RUN_CMD env var if explicitly provided
    2. JAVA_HOME/bin javac/java
    3. PATH-based javac/java
    """
    explicit_cmd = os.getenv("JAVA_COMPILE_RUN_CMD")
    if explicit_cmd:
        return explicit_cmd

    java_home = os.getenv("JAVA_HOME", "").strip()
    if java_home:
        if _is_windows():
            javac = os.path.join(java_home, "bin", "javac.exe")
            java = os.path.join(java_home, "bin", "java.exe")
        else:
            javac = os.path.join(java_home, "bin", "javac")
            java = os.path.join(java_home, "bin", "java")

        return (
            f'"{javac}" Main.java CalculatorService.java ResultFormatter.java'
            f' && "{java}" Main'
        )

    return "javac Main.java CalculatorService.java ResultFormatter.java && java Main"


class CodingTasks:
    @staticmethod
    def get_tasks() -> List[Dict[str, Any]]:
        return [
            {
                "id": 1,
                "type": "debug",
                "difficulty": "easy",
                "language": "python",
                "title": "Fix syntax error in Python function",
                "template_dir": os.path.join(BASE_DIR, "projects", "task1_easy_debug"),
                "expected_fix": "syntax_error",
                "run_command": _python_cmd("main.py"),
                "description": "Fix a Python syntax issue so the program runs correctly.",
                "grader_focus": [
                    "execution_success",
                    "syntax_fix",
                    "behavior_correctness",
                ],
                "expected_output_hint": "Program should print 5.",
                "max_steps": 4,
            },
            {
                "id": 2,
                "type": "refactor",
                "difficulty": "medium",
                "language": "python",
                "title": "Refactor repeated logic into helper function",
                "template_dir": os.path.join(BASE_DIR, "projects", "task2_medium_refactor"),
                "expected_fix": "refactor_repeated_logic",
                "run_command": _python_cmd("app.py"),
                "description": "Reduce code duplication without breaking behavior.",
                "grader_focus": [
                    "execution_success",
                    "duplication_reduction",
                    "helper_reuse",
                    "behavior_preservation",
                ],
                "expected_output_hint": "Program should print 150 twice.",
                "max_steps": 6,
            },
            {
                "id": 3,
                "type": "refactor",
                "difficulty": "hard",
                "language": "java",
                "title": "Fix multi-file Java project logic",
                "template_dir": os.path.join(BASE_DIR, "projects", "task3_hard_java_refactor"),
                "expected_fix": "java_multifile_refactor_fix",
                "run_command": _java_run_command(),
                "description": "Fix interacting Java classes so the full program compiles and runs.",
                "grader_focus": [
                    "compile_success",
                    "logic_fix",
                    "method_alignment",
                    "final_output_correctness",
                ],
                "expected_output_hint": "Final output should include: Result = 15",
                "max_steps": 8,
            },
        ]
