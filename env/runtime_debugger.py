import os
import sys
import shutil
import subprocess
import tempfile
from typing import Dict


def _find_java_bin(bin_name: str) -> str:
    java_home = os.getenv("JAVA_HOME", "").strip()
    if java_home:
        candidate = os.path.join(
            java_home,
            "bin",
            f"{bin_name}.exe" if os.name == "nt" else bin_name,
        )
        if os.path.exists(candidate):
            return candidate

    found = shutil.which(bin_name)
    if found:
        return found

    if os.name == "nt":
        common_roots = [
            r"C:\Program Files\Java",
            r"C:\Program Files (x86)\Java",
        ]
        for root in common_roots:
            if not os.path.isdir(root):
                continue
            try:
                entries = sorted(os.listdir(root), reverse=True)
            except Exception:
                entries = []
            for entry in entries:
                candidate = os.path.join(
                    root,
                    entry,
                    "bin",
                    f"{bin_name}.exe",
                )
                if os.path.exists(candidate):
                    return candidate

    return bin_name


PYTHON_EXE = sys.executable or shutil.which("python") or "python"
JAVA_EXE = _find_java_bin("java")
JAVAC_EXE = _find_java_bin("javac")
CPP_EXE = shutil.which("g++") or "g++"


class RuntimeDebugger:
    @staticmethod
    def analyze_code(language: str, code: str) -> Dict[str, str]:
        language = str(language or "python").lower().strip()
        code = str(code or "")

        if not code.strip():
            return {
                "status": "error",
                "message": "No code provided.",
                "stdout": "",
                "stderr": "",
                "hint": "Paste some code first.",
            }

        if language == "python":
            return RuntimeDebugger._run_python(code)

        if language == "java":
            return RuntimeDebugger._run_java(code)

        if language == "cpp":
            return RuntimeDebugger._run_cpp(code)

        return {
            "status": "error",
            "message": f"Unsupported language: {language}",
            "stdout": "",
            "stderr": "",
            "hint": "Choose python, java, or cpp.",
        }

    @staticmethod
    def _run_python(code: str) -> Dict[str, str]:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = os.path.join(tmpdir, "main.py")

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code)

                result = subprocess.run(
                    [PYTHON_EXE, file_path],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                status = "success" if result.returncode == 0 else "error"

                return {
                    "status": status,
                    "message": "Python code executed." if status == "success" else "Python execution failed.",
                    "stdout": result.stdout or "",
                    "stderr": result.stderr or "",
                    "hint": RuntimeDebugger._basic_hint("python", result.stderr or ""),
                }

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "Python execution timed out.",
                "stdout": "",
                "stderr": "Execution exceeded 5 seconds.",
                "hint": "Check for infinite loops or blocking input.",
            }

        except Exception as e:
            return {
                "status": "error",
                "message": "Python runner crashed.",
                "stdout": "",
                "stderr": str(e),
                "hint": f"Python executable used: {PYTHON_EXE}",
            }

    @staticmethod
    def _run_java(code: str) -> Dict[str, str]:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                file_path = os.path.join(tmpdir, "Main.java")

                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(code)

                compile_result = subprocess.run(
                    [JAVAC_EXE, file_path],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )

                if compile_result.returncode != 0:
                    return {
                        "status": "error",
                        "message": "Java compilation failed.",
                        "stdout": compile_result.stdout or "",
                        "stderr": compile_result.stderr or "",
                        "hint": RuntimeDebugger._basic_hint("java", compile_result.stderr or ""),
                    }

                run_result = subprocess.run(
                    [JAVA_EXE, "-cp", tmpdir, "Main"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                status = "success" if run_result.returncode == 0 else "error"

                return {
                    "status": status,
                    "message": "Java code executed." if status == "success" else "Java runtime failed.",
                    "stdout": run_result.stdout or "",
                    "stderr": run_result.stderr or "",
                    "hint": RuntimeDebugger._basic_hint("java", run_result.stderr or ""),
                }

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "Java execution timed out.",
                "stdout": "",
                "stderr": "Execution exceeded allowed time.",
                "hint": "Check for infinite loops or blocking input.",
            }

        except Exception as e:
            return {
                "status": "error",
                "message": "Java runner crashed.",
                "stdout": "",
                "stderr": str(e),
                "hint": f"Java executables used: javac={JAVAC_EXE}, java={JAVA_EXE}",
            }

    @staticmethod
    def _run_cpp(code: str) -> Dict[str, str]:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                source_path = os.path.join(tmpdir, "main.cpp")
                exe_path = os.path.join(tmpdir, "main.exe" if os.name == "nt" else "main")

                with open(source_path, "w", encoding="utf-8") as f:
                    f.write(code)

                compile_result = subprocess.run(
                    [CPP_EXE, source_path, "-o", exe_path],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if compile_result.returncode != 0:
                    return {
                        "status": "error",
                        "message": "C++ compilation failed.",
                        "stdout": compile_result.stdout or "",
                        "stderr": compile_result.stderr or "",
                        "hint": RuntimeDebugger._basic_hint("cpp", compile_result.stderr or ""),
                    }

                run_result = subprocess.run(
                    [exe_path],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                status = "success" if run_result.returncode == 0 else "error"

                return {
                    "status": status,
                    "message": "C++ code executed." if status == "success" else "C++ runtime failed.",
                    "stdout": run_result.stdout or "",
                    "stderr": run_result.stderr or "",
                    "hint": RuntimeDebugger._basic_hint("cpp", run_result.stderr or ""),
                }

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "C++ execution timed out.",
                "stdout": "",
                "stderr": "Execution exceeded allowed time.",
                "hint": "Check for infinite loops or blocking input.",
            }

        except Exception as e:
            return {
                "status": "error",
                "message": "C++ runner crashed.",
                "stdout": "",
                "stderr": str(e),
                "hint": f"C++ compiler used: {CPP_EXE}",
            }

    @staticmethod
    def _basic_hint(language: str, stderr: str) -> str:
        s = (stderr or "").lower().strip()

        if not s:
            return "No obvious error detected."

        if language == "python":
            if "syntaxerror" in s:
                return "There is a Python syntax issue. Check colons, parentheses, or indentation."
            if "indentationerror" in s:
                return "Indentation is incorrect. Align blocks consistently."
            if "nameerror" in s:
                return "A variable or function name is being used before definition."
            if "typeerror" in s:
                return "A value of the wrong type is being used."

        if language == "java":
            if "expected" in s:
                return "Java compiler expected a missing token such as ';', ')', or '}'."
            if "cannot find symbol" in s:
                return "A variable, method, or class name is unresolved."
            if "class main is public" in s:
                return "The public class name must match the file name Main.java."

        if language == "cpp":
            if "expected" in s:
                return "C++ parser expected a missing symbol like ';', ')', or '}'."
            if "was not declared" in s:
                return "A variable or function is being used before declaration."
            if "undefined reference" in s:
                return "A function was declared but not linked or defined properly."

        return "The compiler/runtime returned an error. Review stderr for exact details."

