from env.coding_env import CodingAssistantEnv

env = CodingAssistantEnv()

state = env.reset(task_id=1)
print("Initial State:")
print(state)

state, reward, done, info = env.step({"tool": "list_files"})
print("\nAfter list_files:")
print("Reward:", reward)
print("Done:", done)
print("Info:", info)

state, reward, done, info = env.step({"tool": "read_file", "path": "main.py"})
print("\nAfter read_file:")
print("Reward:", reward)
print("Done:", done)
print("Info:", info)

fixed_code = """
def add(a,b):
    return a+b


print(add(2, 3))
"""

state, reward, done, info = env.step({
    "tool": "write_file",
    "path": "main.py",
    "content": fixed_code
})
print("\nAfter write_file:")
print("Reward:", reward)
print("Done:", done)
print("Info:", info)

run_cmd = env.current_task["run_command"]

state, reward, done, info = env.step({
    "tool": "run_command",
    "command": run_cmd
})
print("\nAfter run_command:")
print("Reward:", reward)
print("Done:", done)
print("Info:", info)
