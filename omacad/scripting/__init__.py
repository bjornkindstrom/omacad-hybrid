"""User scripts: Python files in the scripts folder that build geometry through a stable API (`api.ScriptContext`).
See GUIDE.md (also what the AI gets when the user asks it to write a script)."""
from omacad.scripting.loader import Param, ScriptError, ScriptInfo, read_info, resolve_values
from omacad.scripting.runner import RunResult, ScriptRunError, check_file_for, check_report, check_script, run_script

__all__ = ["Param", "ScriptError", "ScriptInfo", "read_info", "resolve_values", "RunResult", "ScriptRunError",
           "check_file_for", "check_report", "check_script", "run_script"]
