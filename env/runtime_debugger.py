import os
import tempfile
import subprocess
from typing import Dict

# PYTHON_EXE = r"C:/Users/rajbo/anaconda3/python.exe"
# JAVA_EXE = r"C:/Program Files/Java/jdk1.8.0_202/bin/java.exe"
# JAVAC_EXE = r"C:/Program Files/Java/jdk1.8.0_202/bin/javac.exe"

# PYTHON_EXE = "python3"
# JAVA_EXE = "java"
# JAVAC_EXE = "javac"

PYTHON_EXE = "py"
JAVA_EXE = r"C:\Program Files\Java\jdk1.8.0_202\bin\java.exe"
JAVAC_EXE = r"C:\Program Files\Java\jdk1.8.0_202\bin\javac.exe"

class RuntimeDebugger:
    @staticmethod
    def analyze_code(language: str, code: str) -> Dict[str, str]:
        language = language.lower().strip()

        if not code.strip():
            return {
                "status": "error",
                "message": "No code provided.",
                "stdout": "",
                "stderr": "",
                "hint": "Paste some code first."
            }

        if language == "python":
            return RuntimeDebugger._run_python(code)

        elif language == "java":
            return RuntimeDebugger._run_java(code)

        elif language == "cpp":
            return RuntimeDebugger._run_cpp(code)

        return {
            "status": "error",
            "message": f"Unsupported language: {language}",
            "stdout": "",
            "stderr": "",
            "hint": "Choose python, java, or cpp."
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
                    timeout=5
                )

                status = "success" if result.returncode == 0 else "error"
                hint = RuntimeDebugger._basic_hint("python", result.stderr)

                return {
                    "status": status,
                    "message": "Python code executed." if status == "success" else "Python execution failed.",
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "hint": hint
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "Python execution timed out.",
                "stdout": "",
                "stderr": "Execution exceeded 5 seconds.",
                "hint": "Check for infinite loops or blocking input."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": "Python runner crashed.",
                "stdout": "",
                "stderr": str(e),
                "hint": "Verify Python is installed and accessible."
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
                        timeout=8
                    )

                if compile_result.returncode != 0:
                    return {
                        "status": "error",
                        "message": "Java compilation failed.",
                        "stdout": compile_result.stdout,
                        "stderr": compile_result.stderr,
                        "hint": RuntimeDebugger._basic_hint("java", compile_result.stderr)
                    }

                run_result = subprocess.run(
                    [JAVA_EXE, "-cp", tmpdir, "Main"],
                        capture_output=True,
                        text=True,
                        timeout=5
                )

                status = "success" if run_result.returncode == 0 else "error"
    
                return {
                    "status": status,
                    "message": "Java code executed." if status == "success" else "Java runtime failed.",
                    "stdout": run_result.stdout,
                    "stderr": run_result.stderr,
                    "hint": RuntimeDebugger._basic_hint("java", run_result.stderr)
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "Java execution timed out.",
                "stdout": "",
                "stderr": "Execution exceeded allowed time.",
                "hint": "Check for infinite loops or blocking input."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": "Java runner crashed.",
                "stdout": "",
                "stderr": str(e),
                "hint": "Make sure javac and java are available in the same terminal session."
            }

    @staticmethod
    def _run_cpp(code: str) -> Dict[str, str]:
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                source_path = os.path.join(tmpdir, "main.cpp")
                exe_path = os.path.join(tmpdir, "main.exe")

                with open(source_path, "w", encoding="utf-8") as f:
                    f.write(code)

                compile_result = subprocess.run(
                    ["g++", source_path, "-o", exe_path],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                if compile_result.returncode != 0:
                    return {
                        "status": "error",
                        "message": "C++ compilation failed.",
                        "stdout": compile_result.stdout,
                        "stderr": compile_result.stderr,
                        "hint": RuntimeDebugger._basic_hint("cpp", compile_result.stderr)
                    }

                run_result = subprocess.run(
                    [exe_path],
                    capture_output=True,
                    text=True,
                    timeout=5
                )

                status = "success" if run_result.returncode == 0 else "error"

                return {
                    "status": status,
                    "message": "C++ code executed." if status == "success" else "C++ runtime failed.",
                    "stdout": run_result.stdout,
                    "stderr": run_result.stderr,
                    "hint": RuntimeDebugger._basic_hint("cpp", run_result.stderr)
                }
        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "message": "C++ execution timed out.",
                "stdout": "",
                "stderr": "Execution exceeded allowed time.",
                "hint": "Check for infinite loops or blocking input."
            }
        except Exception as e:
            return {
                "status": "error",
                "message": "C++ runner crashed.",
                "stdout": "",
                "stderr": str(e),
                "hint": "Make sure g++ is available in the same terminal session."
            }

    @staticmethod
    def _basic_hint(language: str, stderr: str) -> str:
        s = (stderr or "").lower()

        if not s.strip():
            return "No obvious error detected."

        if language == "python":
            if "syntaxerror" in s:
                return "There is a Python syntax issue. Check colons, parentheses, or indentation."
            if "indentationerror" in s:
                return "Indentation is incorrect. Align blocks consistently."
            if "nameerror" in s:
                return "A variable or function name is being used before definition."

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