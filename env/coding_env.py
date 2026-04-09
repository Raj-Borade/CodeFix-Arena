from typing import Any, Dict, Optional, Tuple

from tasks.coding_tasks import CodingTasks
from env.workspace import WorkspaceManager
from env.grader import CodingTaskGrader
from env.models import ActionModel, ObservationModel


class CodingAssistantEnv:
    MIN_REWARD = 0.01
    MAX_REWARD = 0.95
    
    def _sanitize_info(self, info: Dict[str, Any]) -> Dict[str, Any]:
        clean = {}

        for k, v in info.items():
            key = str(k).lower()

            # REMOVE risky numeric keys
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
            nested = {}
            for nk, nv in v.items():
                if isinstance(nv, (int, float, bool)):
                    continue
                nested[nk] = nv
            clean[k] = nested
        else:
            clean[k] = v

            return clean

    def __init__(self):
        self.state_data: Dict[str, Any] = {}
        self.current_task: Optional[Dict[str, Any]] = None
        self.done: bool = False
        self.max_steps: int = 6
        self.tasks = CodingTasks.get_tasks()
        self.workspace = WorkspaceManager()
        self.last_command_result: Dict[str, str] = self._empty_command_result()

    def _empty_command_result(self) -> Dict[str, str]:
        return {"status": "", "stdout": "", "stderr": ""}

    def _safe_reward(self, reward: Any) -> float:
        try:
            reward = float(reward)
        except Exception:
            return self.MIN_REWARD

        # STRICT clamp (NO rounding risk)
        if reward <= 0.0:
            return self.MIN_REWARD
        if reward >= 1.0:
            return self.MAX_REWARD

        # extra safety
        reward = max(self.MIN_REWARD, min(self.MAX_REWARD, reward))
        return float(f"{reward:.6f}")

    def _sanitize_breakdown(self, breakdown: Dict[str, Any]) -> Dict[str, Any]:
        clean = {}
        for k, v in breakdown.items():
            if isinstance(v, (int, float)):
                clean[k] = self._safe_reward(v)
            else:
                clean[k] = v
        return clean

    def _base_reward_for_tool(self, tool_name: str) -> float:
        tool_rewards = {
            "list_files": 0.02,
            "read_file": 0.03,
            "write_file": 0.05,
            "run_command": 0.06,
        }
        return self._safe_reward(tool_rewards.get(tool_name, self.MIN_REWARD))

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
            reward = self._safe_reward(self.MIN_REWARD)
            return self.state(), reward, True, {
                "message": "Episode already finished",
                "tool_result": {},
                "feedback": "No further actions allowed.",
                "score_breakdown": {"reward": reward},
            }

        try:
            validated = ActionModel(**action)
        except Exception:
            reward = self._safe_reward(self.MIN_REWARD)
            return self.state(), reward, self.done, {
                "message": "Invalid action",
                "tool_result": {},
                "feedback": "Validation failed",
                "score_breakdown": {"reward": reward},
            }

        tool_result, tool_error = self._safe_apply_action(validated)

        self.state_data["step"] += 1
        self.state_data["files"] = self.workspace.list_files()
        self.state_data["last_command_result"] = self.last_command_result

        reward = self._base_reward_for_tool(validated.tool)
        feedback = "Action applied."
        score_breakdown: Dict[str, Any] = {"base_reward": reward}

        if tool_error:
            reward = self._safe_reward(self.MIN_REWARD)
            feedback = f"Tool failed: {tool_error}"
            score_breakdown["reward"] = reward

        elif validated.tool == "run_command":
            graded = CodingTaskGrader.grade(
                self.current_task,
                self.workspace,
                self.last_command_result,
            )

            reward = self._safe_reward(graded.get("reward", reward))
            feedback = graded.get("feedback", "Executed")

            score_breakdown = self._sanitize_breakdown(
                graded.get("score_breakdown", {}) or {}
            )
            score_breakdown["reward"] = reward

            # ❌ REMOVED early done condition (IMPORTANT)
            # if reward >= 0.9:
            #     self.done = True

        else:
            score_breakdown["reward"] = reward

        if self.state_data["step"] >= self.max_steps:
            self.done = True

        reward = self._safe_reward(reward)

        info = {
    "tool_result": tool_result,
    "feedback": feedback,
    "score_breakdown": score_breakdown,
}

        safe_info = self._sanitize_info(info)

        return self.state(), reward, self.done, safe_info
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
            raise ValueError("Task not found")

        return self.tasks[0]

    def _safe_apply_action(self, action: ActionModel) -> Tuple[Dict[str, Any], Optional[str]]:
        try:
            return self._apply_action(action), None
        except Exception as e:
            error_result = {
                "status": "error",
                "stdout": "",
                "stderr": str(e),
            }

            if action.tool == "run_command":
                self.last_command_result = error_result

            return error_result, str(e)

    def _apply_action(self, action: ActionModel) -> Dict[str, Any]:
        if action.tool == "list_files":
            return {"files": self.workspace.list_files()}

        if action.tool == "read_file":
            return {"content": self.workspace.read_file(action.path)}

        if action.tool == "write_file":
            return {"message": self.workspace.write_file(action.path, action.content or "")}

        if action.tool == "run_command":
            result = self.workspace.run_command(action.command)
            self.last_command_result = result
            return result

        raise ValueError("Unknown tool")
