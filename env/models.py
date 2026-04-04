from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class CommandResultModel(BaseModel):
    status: str = Field(default="", description="Execution status such as success, error, or timeout.")
    stdout: str = Field(default="", description="Standard output captured from the last command.")
    stderr: str = Field(default="", description="Standard error captured from the last command.")


class ObservationModel(BaseModel):
    task_id: int = Field(..., description="Unique task identifier.")
    task_type: str = Field(..., description="Task category such as debug or refactor.")
    difficulty: str = Field(..., description="Task difficulty level.")
    language: str = Field(..., description="Primary programming language of the task.")
    title: str = Field(..., description="Human-readable task title.")
    step: int = Field(..., ge=0, description="Current step count in the episode.")
    max_steps: int = Field(..., ge=1, description="Maximum allowed steps in the episode.")
    workspace_dir: str = Field(..., description="Workspace directory for the active task.")
    files: List[str] = Field(default_factory=list, description="List of files currently available in the workspace.")
    last_command_result: CommandResultModel = Field(
        default_factory=CommandResultModel,
        description="Structured result of the most recent command execution."
    )

    model_config = {
        "extra": "forbid"
    }


class ActionModel(BaseModel):
    tool: Literal["list_files", "read_file", "write_file", "run_command"] = Field(
        ...,
        description="Tool/action the agent wants to execute."
    )
    path: Optional[str] = Field(
        default=None,
        description="Target file path for read_file or write_file."
    )
    content: Optional[str] = Field(
        default=None,
        description="New file content for write_file."
    )
    command: Optional[str] = Field(
        default=None,
        description="Shell command to execute for run_command."
    )

    model_config = {
        "extra": "forbid"
    }

    @model_validator(mode="after")
    def validate_tool_payload(self):
        if self.tool == "read_file" and not self.path:
            raise ValueError("read_file requires 'path'")

        if self.tool == "write_file" and not self.path:
            raise ValueError("write_file requires 'path'")

        if self.tool == "run_command" and not self.command:
            raise ValueError("run_command requires 'command'")

        return self
    
    






