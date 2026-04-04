from typing import Any, Dict, Optional, Tuple

from tasks.coding_tasks import CodingTasks
from env.workspace import WorkspaceManager
from env.grader import CodingTaskGrader
from env.models import ActionModel, ObservationModel


class CodingAssistantEnv:
    def __init__(self):
        self.state_data: Dict[str, Any] = {}
        self.current_task: Optional[Dict[str, Any]] = None
        self.done: bool = False
        self.max_steps: int = 6
        self.tasks = CodingTasks.get_tasks()
        self.workspace = WorkspaceManager()
        self.last_command_result: Dict[str, str] = self._empty_command_result()

    def _empty_command_result(self) -> Dict[str, str]:
        return {
            "status": "",
            "stdout": "",
            "stderr": "",
        }

    def reset(self, task_id: Optional[int] = None) -> Dict[str, Any]:
        self.done = False
        self.current_task = self._generate_task(task_id)
        self.max_steps = int(self.current_task.get("max_steps", 6))

        workspace_dir = self.workspace.create_workspace_from_template(
            self.current_task["template_dir"]
        )

        self.last_command_result = self._empty_command_result()

        self.state_data = {
            "task_id": self.current_task.get("id"),
            "task_type": self.current_task.get("type"),
            "difficulty": self.current_task.get("difficulty"),
            "language": self.current_task.get("language"),
            "title": self.current_task.get("title"),
            "step": 0,
            "max_steps": self.max_steps,
            "workspace_dir": workspace_dir,
            "files": self.workspace.list_files(),
            "last_command_result": self.last_command_result,
        }

        return self.state()

    def step(self, action: Dict[str, Any]) -> Tuple[Dict[str, Any], float, bool, Dict[str, Any]]:
        if self.done:
            return self.state(), 0.0, True, {
                "message": "Episode already finished",
                "tool_result": {},
                "feedback": "No further actions allowed after episode completion.",
                "expected_fix": self.current_task.get("expected_fix") if self.current_task else "",
                "score_breakdown": {},
            }

        try:
            validated = ActionModel(**action)
        except Exception as e:
            return self.state(), 0.0, self.done, {
                "message": f"Invalid action: {e}",
                "tool_result": {},
                "feedback": "Action validation failed.",
                "expected_fix": self.current_task.get("expected_fix") if self.current_task else "",
                "score_breakdown": {},
            }

        tool_result, tool_error = self._safe_apply_action(validated)

        self.state_data["step"] += 1
        self.state_data["files"] = self.workspace.list_files()
        self.state_data["last_command_result"] = self.last_command_result

        reward = 0.0
        feedback = "Action applied."
        score_breakdown: Dict[str, Any] = {}

        if tool_error:
            feedback = f"Tool execution failed: {tool_error}"
        elif validated.tool == "run_command":
            graded = CodingTaskGrader.grade(
                self.current_task,
                self.workspace,
                self.last_command_result,
            )
            reward = float(graded.get("reward", 0.0))
            feedback = graded.get("feedback", "Command executed.")
            score_breakdown = graded.get("score_breakdown", {})

            if reward >= 0.9:
                self.done = True

        if self.state_data["step"] >= self.max_steps:
            self.done = True

        info = {
            "tool_result": tool_result,
            "feedback": feedback,
            "expected_fix": self.current_task.get("expected_fix") if self.current_task else "",
            "score_breakdown": score_breakdown,
            "episode_summary": {
                "current_step": self.state_data["step"],
                "max_steps": self.max_steps,
                "done": self.done,
            },
        }

        return self.state(), reward, self.done, info

    def state(self) -> Dict[str, Any]:
        observation = ObservationModel(**self.state_data)
        return observation.model_dump()

    def list_tasks(self):
        return self.tasks

    def _generate_task(self, task_id: Optional[int] = None) -> Dict[str, Any]:
        if task_id is not None:
            for task in self.tasks:
                if task["id"] == task_id:
                    return task
            raise ValueError(f"Task with id {task_id} not found")

        if not self.tasks:
            raise ValueError("No tasks are available in CodingTasks.get_tasks()")

        return self.tasks[0]

    def _safe_apply_action(self, action: ActionModel) -> Tuple[Dict[str, Any], Optional[str]]:
        try:
            return self._apply_action(action), None
        except Exception as e:
            error_result = {
                "status": "error",
                "stdout": "",
                "stderr": str(e),
                "message": str(e),
            }

            if action.tool == "run_command":
                self.last_command_result = error_result

            return error_result, str(e)

    def _apply_action(self, action: ActionModel) -> Dict[str, Any]:
        if action.tool == "list_files":
            return {"files": self.workspace.list_files()}

        if action.tool == "read_file":
            if not action.path:
                raise ValueError("read_file action requires 'path'")
            content = self.workspace.read_file(action.path)
            return {"content": content}

        if action.tool == "write_file":
            if not action.path:
                raise ValueError("write_file action requires 'path'")
            message = self.workspace.write_file(action.path, action.content or "")
            return {"message": message}

        if action.tool == "run_command":
            if not action.command:
                raise ValueError("run_command action requires 'command'")
            result = self.workspace.run_command(action.command)
            self.last_command_result = result
            return result

        raise ValueError(f"Unknown tool: {action.tool}")


