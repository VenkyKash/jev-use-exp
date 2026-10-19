"""Task Contextualizer / Pre-flight Compiler for Jev using agy CLI with strict JSON schema.

Uses the fastest/lowest tier model (gemini-3.6-flash-low, reasoning effort low)
and --json-schema to produce strictly validated Task definitions with input_purposes
and success criteria, keeping loose limits out of literal typing inputs.
"""

import os
import json
import subprocess
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List

SCHEMA_PATH = Path(__file__).parent / "task_schema.json"

COMPILE_PROMPT_TEMPLATE = """You are a minimal task compiler for a computer-use decision model (Jev).
Jev decides ALL UI actions, clicks, regions, and apps autonomously. It cannot synthesize math, sequences, or look up paths.
Your ONLY job is to compile the user request into a strictly validated Task definition.

User Request: {user_prompt}

Rules:
1. "goal": Clear, declarative goal describing the desired end state. Mention boundaries (e.g. 'limit to 30') in the goal text or brief.success, NEVER as a raw input.
2. "app": The target application display name.
3. "inputs": A list of up to 8 exact literal strings, formulas, numbers, or file paths that the task will actually require typing into UI controls/cells.
4. "brief.input_purposes": Array of strings matching the "inputs" array 1-to-1, describing what each literal is and where it belongs (e.g. "Header for Column A (Even numbers)", "First even number in row 2", "Formula to increment even numbers down column A").
5. "brief.success": 1 to 3 observable conditions indicating the task is finished (e.g. "Column A and B contain even/odd numbers reaching 30").
6. "checks": Empty list [].
"""

def compile_prompt_with_direct_api(user_prompt: str) -> dict:
    """Fallback when agy CLI is not present in environment (e.g. cloud VM with API keys)."""
    import urllib.request
    import json
    
    schema = json.loads(SCHEMA_PATH.read_text())
    prompt = COMPILE_PROMPT_TEMPLATE.format(user_prompt=user_prompt)
    
    # 1. Thinky / Tinker OpenAI-compatible endpoint via THINKY_API_ENDPOINT & THINKY_API_KEY
    thinky_key = os.getenv("THINKY_API_KEY")
    if thinky_key:
        thinky_url = os.getenv(
            "THINKY_API_ENDPOINT",
            "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1/chat/completions"
        )
        payload = {
            "model": os.getenv("THINKY_MODEL", "thinkingmachines/Inkling"),
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "compiled_task",
                    "strict": True,
                    "schema": schema
                }
            }
        }
        req = urllib.request.Request(
            thinky_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {thinky_key}"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            # Handle possible markdown fencing from proxies
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                content = "\n".join(lines).strip()
            return json.loads(content)

    # 2. Google Gemini API via GEMINI_API_KEY
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={gemini_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "response_schema": schema
            }
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)

    # 3. Standard OpenAI API via OPENAI_API_KEY
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        url = "https://api.openai.com/v1/chat/completions"
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "compiled_task",
                    "strict": True,
                    "schema": schema
                }
            }
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {openai_key}"
            }
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            text = data["choices"][0]["message"]["content"]
            return json.loads(text)
            
    raise RuntimeError(
        "Neither 'agy' CLI nor 'THINKY_API_KEY', 'GEMINI_API_KEY', or 'OPENAI_API_KEY' is configured. "
        "Provision THINKY_API_KEY to compile natural language tasks."
    )

def compile_prompt_with_agy(user_prompt: str, model: str = "gemini-3.6-flash-low") -> dict:
    """Invokes agy with gemini-3.6-flash-low, effort low, and --json-schema, falling back to direct API."""
    import shutil
    if not shutil.which("agy"):
        return compile_prompt_with_direct_api(user_prompt)

    prompt = COMPILE_PROMPT_TEMPLATE.format(user_prompt=user_prompt)
    cmd = [
        "agy",
        "--model", model,
        "--effort", "low",
        "--disable-slash-commands",
        "--json-schema", str(SCHEMA_PATH),
        "--output-format", "json",
        "--print-timeout", "25s",
        "--print", prompt
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        raw = result.stdout.strip()
    except Exception:
        # Fallback to direct API if agy execution fails
        return compile_prompt_with_direct_api(user_prompt)
    
    # Strip markdown fences if present
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw = "\n".join(lines).strip()
        
    envelope = json.loads(raw)
    data = envelope.get("structured_output") or envelope
    
    # Validate 1-to-1 matching between inputs and input_purposes
    inputs = data.get("inputs", [])
    brief = data.get("brief", {})
    purposes = brief.get("input_purposes", [])
    if len(purposes) < len(inputs):
        for i in range(len(purposes), len(inputs)):
            purposes.append(f"Value '{inputs[i]}'")
        brief["input_purposes"] = purposes
    elif len(purposes) > len(inputs):
        brief["input_purposes"] = purposes[:len(inputs)]
        
    return data

def compile_and_save(user_prompt: str, out_path: Path, model: str = "gemini-3.6-flash-low") -> Path:
    task_data = compile_prompt_with_agy(user_prompt, model=model)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(task_data, indent=2))
    return out_path

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python compile_task.py <prompt> [output_path]")
        sys.exit(1)
    prompt_arg = sys.argv[1]
    dest = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("tasks/compiled_task.json")
    saved = compile_and_save(prompt_arg, dest)
    print(f"Task compiled and saved to {saved}:")
    print(saved.read_text())
