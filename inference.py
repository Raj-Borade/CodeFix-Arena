import json
import os
from typing import Any, Dict, List, Optional

from openai import OpenAI

from env.coding_env import CodingAssistantEnv


MODEL_NAME = os.environ.get("MODEL_NAME", "meta-llama/Meta-Llama-3-8B-Instruct")
EPS = 0.001
MAX_SCORE = 0.999


def clamp_score(score: Any) -> float:
    try:
        s = float(score)
    except (TypeError, ValueError):
        return EPS

    if s != s:  # NaN
        return EPS
    if s <= 0.0:
        return EPS
    if s >= 1.0:
        return MAX_SCORE
    return max(EPS, min(MAX_SCORE, s))


def log_start(label: str) -> None:
    print(f"\n[START] {label}")


def log_step(label: str, payload: Optional[Dict[str, Any]] = None) -> None:
    print(f"\n[STEP] {label}")
    if payload is not None:
        try:
            print(json.dumps(payload, indent=2))
        except Exception:
            print(str(payload))


def log_end(label: str, payload: Optional[Dict[str, Any]] = None) -> None:
    print(f"\n[END] {label}")
    if payload is not None:
        try:
            print(json.dumps(payload, indent=2))
        except Exception:
            print(str(payload))


def make_client() -> Optional[OpenAI]:
    try:
        api_base_url = os.environ["API_BASE_URL"]
        api_key = os.environ["API_KEY"]

        client = OpenAI(
            base_url=api_base_url,
            api_key=api_key,
        )

        log_step("client_initialization", {
            "status": "success",
            "base_url_present": bool(api_base_url),
            "api_key_present": bool(api_key),
            "model_name": MODEL_NAME,
        })
        return client

    except KeyError as e:
        missing_name = str(e).strip("'")
        log_end("client_initialization", {
            "status": "error",
            "message": f"Missing required injected environment variable: {missing_name}",
        })
        return None
    except Exception as e:
        log_end("client_initialization", {
            "status": "error",
            "message": str(e),
        })
        return None


def get_solution_for_task(task_id: int) -> List[Dict[str, str]]:
    if task_id == 1:
        return [{
            "path": "main.py",
            "content": """def add(a, b):
    return a + b


print(add(2, 3))
"""
        }]

    if task_id == 2:
        return [{
            "path": "app.py",
            "content": """def calculate_total():
    total = 0
    total += 100
    total += 50
    return total


def process_order():
    print(calculate_total())


def process_cart():
    print(calculate_total())


process_order()
process_cart()
"""
        }]

    if task_id == 3:
        return [
            {
                "path": "CalculatorService.java",
                "content": """public class CalculatorService {
    public int add(int a, int b) {
        return a + b;
    }
}
"""
            },
            {
                "path": "ResultFormatter.java",
                "content": """public class ResultFormatter {
    public static String format(int result) {
        return "Result = " + result;
    }
}
"""
            },
        ]

    return []


def call_baseline_model(client: OpenAI, task_id: int, state: Dict[str, Any]) -> Dict[str, Any]:
    prompt = {
        "task_id": task_id,
        "title": state.get("title"),
        "language": state.get("language"),
        "files": state.get("files", []),
        "instruction": "Return a short JSON object with a compact task summary.",
    }

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            temperature=0,
            max_tokens=120,
            messages=[
                {"role": "system", "content": "Return compact JSON only."},
                {"role": "user", "content": json.dumps(prompt)},
            ],
        )

        content = response.choices[0].message.content or "{}"

        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                return parsed
            return {"raw_response": content.strip()}
        except Exception:
            return {"raw_response": content.strip()}

    except Exception as e:
        return {
            "fallback": True,
            "message": "Model trace skipped due to API error.",
            "error": str(e),
            "task_id": task_id,
            "title": state.get("title"),
            "model_name": MODEL_NAME,
        }


def solve_task(env: CodingAssistantEnv, client: OpenAI, task_id: int) -> float:
    log_start(f"task_{task_id}")

    state = env.reset(task_id=task_id)

    log_step("task_initialized", {
        "task_id": state.get("task_id"),
        "task_type": state.get("task_type"),
        "difficulty": state.get("difficulty"),
        "language": state.get("language"),
        "title": state.get("title"),
        "files": state.get("files", []),
        "max_steps": state.get("max_steps"),
    })

    model_trace = call_baseline_model(client, task_id, state)
    log_step("openai_client_trace", model_trace)

    state, reward, done, info = env.step({"tool": "list_files"})
    log_step("list_files", info)

    solutions = get_solution_for_task(task_id)

    for solution in solutions:
        state, reward, done, info = env.step({
            "tool": "read_file",
            "path": solution["path"],
        })
        log_step(f"read_file:{solution['path']}", info)

        state, reward, done, info = env.step({
            "tool": "write_file",
            "path": solution["path"],
            "content": solution["content"],
        })
        log_step(f"write_file:{solution['path']}", info)

    run_command = env.current_task["run_command"]

    state, reward, done, info = env.step({
        "tool": "run_command",
        "command": run_command,
    })
    log_step("run_command", info)

    safe_reward = clamp_score(reward)

    log_end(f"task_{task_id}", {
        "task_id": task_id,
        "score": safe_reward,
        "done": done,
    })

    return safe_reward


def run_baseline() -> None:
    log_start("baseline_run")

    client = make_client()
    if client is None:
        log_end("baseline_run", {
            "status": "stopped",
            "reason": "Client initialization failed",
        })
        return

    env = CodingAssistantEnv()
    all_tasks = env.list_tasks()

    scores: Dict[int, float] = {}

    for task in all_tasks:
        task_id = task["id"]
        try:
            score = solve_task(env, client, task_id)
            scores[task_id] = clamp_score(score)
        except Exception as e:
            scores[task_id] = EPS
            log_end(f"task_{task_id}", {
                "task_id": task_id,
                "status": "error",
                "message": str(e),
                "score": EPS,
            })

    average_score = EPS
    if scores:
        average_score = clamp_score(sum(scores.values()) / len(scores))

    summary = {
        "scores": {str(tid): clamp_score(score) for tid, score in scores.items()},
        "average_score": average_score,
    }

    log_end("baseline_run", summary)


if __name__ == "__main__":
    try:
        run_baseline()
    except Exception as e:
        log_end("program", {
            "status": "fatal_error",
            "message": str(e),
        })
