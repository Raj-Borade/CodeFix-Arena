import os
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional


class WorkspaceManager:
    def __init__(self):
        self.workspace_dir: Optional[str] = None

    def create_workspace_from_template(self, template_dir: str) -> str:
        self.cleanup()

        if not os.path.exists(template_dir):
            raise FileNotFoundError(f"Template directory does not exist: {template_dir}")

        if not os.path.isdir(template_dir):
            raise NotADirectoryError(f"Template path is not a directory: {template_dir}")

        self.workspace_dir = tempfile.mkdtemp(prefix="codefix_workspace_")
        self._copy_tree(template_dir, self.workspace_dir)
        return self.workspace_dir

    def cleanup(self) -> None:
        if self.workspace_dir and os.path.exists(self.workspace_dir):
            shutil.rmtree(self.workspace_dir, ignore_errors=True)
        self.workspace_dir = None

    def _copy_tree(self, src: str, dst: str) -> None:
        found_any_file = False

        for root, dirs, files in os.walk(src):
            rel_root = os.path.relpath(root, src)
            target_root = dst if rel_root == "." else os.path.join(dst, rel_root)
            os.makedirs(target_root, exist_ok=True)

            for directory in dirs:
                os.makedirs(os.path.join(target_root, directory), exist_ok=True)

            for filename in files:
                found_any_file = True
                src_file = os.path.join(root, filename)
                dst_file = os.path.join(target_root, filename)
                shutil.copy2(src_file, dst_file)

        if not found_any_file:
            raise FileNotFoundError(f"No files found inside template directory: {src}")

    def list_files(self) -> List[str]:
        if not self.workspace_dir:
            return []

        result: List[str] = []
        for root, _, files in os.walk(self.workspace_dir):
            for filename in files:
                full_path = os.path.join(root, filename)
                rel_path = os.path.relpath(full_path, self.workspace_dir)
                result.append(rel_path.replace("\\", "/"))

        return sorted(result)

    def read_file(self, path: str) -> str:
        full_path = self._safe_path(path)

        if not os.path.exists(full_path):
            raise FileNotFoundError(f"File not found: {path}")

        if not os.path.isfile(full_path):
            raise ValueError(f"Path is not a file: {path}")

        with open(full_path, "r", encoding="utf-8") as f:
            return f.read()

    def write_file(self, path: str, content: str) -> str:
        full_path = self._safe_path(path)
        parent_dir = os.path.dirname(full_path)

        if parent_dir:
            os.makedirs(parent_dir, exist_ok=True)

        with open(full_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)

        return f"Wrote file: {path}"

    def run_command(self, command: str, timeout: int = 10) -> Dict[str, str]:
        if not self.workspace_dir:
            return {
                "status": "error",
                "stdout": "",
                "stderr": "Workspace not initialized.",
            }

        command = (command or "").strip()
        if not command:
            return {
                "status": "error",
                "stdout": "",
                "stderr": "Empty command provided.",
            }

        try:
            result = subprocess.run(
                command,
                shell=True,
                cwd=self.workspace_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            return {
                "status": "success" if result.returncode == 0 else "error",
                "stdout": result.stdout or "",
                "stderr": result.stderr or "",
            }

        except subprocess.TimeoutExpired:
            return {
                "status": "error",
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds.",
            }
        except Exception as e:
            return {
                "status": "error",
                "stdout": "",
                "stderr": str(e),
            }

    def _safe_path(self, relative_path: str) -> str:
        if not self.workspace_dir:
            raise ValueError("Workspace not initialized.")

        if not relative_path or not relative_path.strip():
            raise ValueError("Path cannot be empty.")

        normalized = os.path.normpath(relative_path).replace("\\", "/")
        full_path = os.path.abspath(os.path.join(self.workspace_dir, normalized))
        workspace_abs = os.path.abspath(self.workspace_dir)

        try:
            common_path = os.path.commonpath([workspace_abs, full_path])
        except ValueError:
            raise ValueError("Unsafe path access detected.")

        if common_path != workspace_abs:
            raise ValueError("Unsafe path access detected.")

        return full_path
    
    















