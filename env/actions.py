from typing import Optional, Literal
from pydantic import BaseModel


class AgentAction(BaseModel):
    tool: Literal["list_files", "read_file", "write_file", "run_command"]
    path: Optional[str] = None
    content: Optional[str] = None
    command: Optional[str] = None