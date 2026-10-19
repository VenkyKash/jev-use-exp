import asyncio
import time
import os
import json
import re
from dataclasses import asdict
from pathlib import Path

from core import Candidate
from native_core import verify
from evidence import evidence_handoff
from native_errors import error_details
from native_driver import select_window
from jev_adapter import checked_system_one
from driver_candidates import thaw
from v2_payload.perception import (
    parse_raw_regions,
    cluster_into_lines,
    format_visual_lines_for_prompt,
    should_trigger_adaptive_perception,
    build_visual_click_candidates,
)

MENU_STOPWORDS = {
    "a", "an", "the", "and", "or", "to", "in", "for", "of", "with", "at", "by", "from", "launch", "app",
    "create", "make", "list", "do", "get", "go", "show", "set", "use", "containing", "limited", "limit"
}

class ChoiceV2:
    def __init__(self, instructions: str, criteria: dict):
        self.type = "choice"
        self.instructions = instructions
        self.criteria = criteria
        
    def to_dict(self):
        return {
            "type": self.type,
            "instructions": self.instructions,
            "criteria": self.criteria
        }

async def choose_v2(client, request: dict):
    import copy
    from typesafe_sdk import Choice
    
    questions = {}
    for key, q in request.get("questions", {}).items():
        questions[key] = Choice(instructions=q["instructions"], criteria=q["criteria"])
        
    state = request.get("state", {})
    response = checked_system_one(client.client, state=state, questions=questions)
    return response

async def get_running_windows(driver):
    try:
        apps_res = await driver.call("list_apps", {})
        apps = apps_res.get("apps", [])
    except Exception:
        apps = []
        
    windows = []
    for app in apps:
        pid = app.get("pid")
        app_name = app.get("name", "Unknown App")
        try:
            win_res = await driver.call("list_windows", {"pid": pid})
            for w in win_res.get("windows", []):
                # Include window if it has a title and non-zero dimensions
                bounds = w.get("bounds", {})
                has_size = bounds.get("width", 0) > 0 and bounds.get("height", 0) > 0
                if w.get("title") and (w.get("is_on_screen") or has_size):
                    windows.append({
                        "pid": pid,
                        "window_id": w["window_id"],
                        "app_name": app_name,
                        "title": w["title"],
                        "active": app.get("active", False)
                    })
        except Exception:
            pass
    return windows

def get_installed_apps(page=0, page_size=25):
    apps = []
    for app_dir in ["/Applications", "/System/Applications", os.path.expanduser("~/Applications")]:
        try:
            for item in os.listdir(app_dir):
                if item.endswith(".app"):
                    apps.append(item[:-4])
        except Exception:
            pass
    apps = sorted(list(set(apps)))
    start = page * page_size
    end = start + page_size
    return apps[start:end], end < len(apps)

def get_app_descriptor(app_name: str) -> str:
    name_clean = app_name.strip().lower()
    descriptors = {
        "gridcraft": "spreadsheet", "filmcraft": "video editor",
        "soundcraft": "digital audio workstation",
        "google chrome": "web browser", "chrome": "web browser",
        "safari": "web browser", "brave browser": "web browser",
        "firefox": "web browser", "edge": "web browser",
        "visual studio code": "code editor", "code": "code editor",
        "cursor": "code editor", "xcode": "ide",
        "notes": "note editor", "textedit": "text editor",
        "calculator": "calculator", "calendar": "calendar",
        "messages": "messaging", "mail": "email client",
        "terminal": "terminal", "iterm2": "terminal",
        "system settings": "settings", "finder": "file manager"
    }
    return descriptors.get(name_clean, "app")

def format_goal(goal: str) -> str:
    return (
        "You're a computer-use agent that is making real-time decisions based on the UI tree "
        "that you receive to navigate the console to accomplish the user's request below. "
        "Sometimes you would have to look through different hierarchies in the UI tree to get to "
        "the right destination. When entering data in grids, forms, or documents, check your active "
        "position and align horizontally and vertically before typing. The goal is to be able to "
        "accomplish this task -- feel free to take liberty in exploring a console if you don't "
        "understand it at first. "
        f"{goal}"
    )

async def step_0_app_choice(task, driver, chooser, emit, dry_run=False, current_page=0, current_target=None):
    running_windows = await get_running_windows(driver)
    installed_apps, has_more = get_installed_apps(page=current_page)
    
    criteria = {}
    window_map = {}
    app_map = {}
    
    if current_target is not None:
        c_pid, c_win_id = current_target
        current_win = next((w for w in running_windows if w["pid"] == c_pid and w["window_id"] == c_win_id), None)
        if current_win:
            desc = get_app_descriptor(current_win["app_name"])
            criteria["current"] = f"Continue working in {current_win['app_name']} window '{current_win['title']}' ({desc}, currently active)"
            window_map["current"] = current_win

    for i, w in enumerate(running_windows):
        key = f"w_{i}"
        frontmost = ", frontmost" if w["active"] else ""
        desc = get_app_descriptor(w["app_name"])
        criteria[key] = f"{w['app_name']} window '{w['title']}' ({desc}, running{frontmost})"
        window_map[key] = w
        
    for i, app_name in enumerate(installed_apps):
        key = f"launch_{i}"
        desc = get_app_descriptor(app_name)
        criteria[key] = f"Launch {app_name} ({desc}, installed, not running)"
        app_map[key] = app_name
        
    if has_more:
        criteria["more_apps"] = "The required application is not in this list; show the next page of installed apps"
    criteria["cannot"] = "I have checked all pages and the required application is not installed; hand off to the user"
    
    state = {
        "goal": format_goal(task.goal),
        "worked": [],
        "did_not_work": []
    }
    if current_target is not None and "current" in window_map:
        cw = window_map["current"]
        state["current_app"] = f"{cw['app_name']} window '{cw['title']}' ({get_app_descriptor(cw['app_name'])})"
        
    request = {
        "state": state,
        "questions": {
            "app": {
                "type": "choice",
                "instructions": "Which application window should be used to accomplish the goal?",
                "criteria": criteria
            }
        }
    }
    
    emit(dict(event="v2_step_0_request", request=request))
    if dry_run:
        return "dry_run"
        
    response = await choose_v2(chooser, request)
    answer = response.choices["app"]
    choice_id = answer.choice
    
    emit(dict(event="v2_step_0_decision", choice=choice_id))
    
    if choice_id == "cannot":
        return "abstained"
    elif choice_id == "more_apps":
        return await step_0_app_choice(task, driver, chooser, emit, dry_run, current_page + 1, current_target)
    elif choice_id in window_map:
        w = window_map[choice_id]
        if driver.accepts("bring_to_front", {"pid": w["pid"], "window_id": w["window_id"]}):
            try:
                await driver.call("bring_to_front", {"pid": w["pid"], "window_id": w["window_id"]})
                await asyncio.sleep(0.5)
            except Exception:
                pass
        return (w["pid"], w["window_id"])
    elif choice_id in app_map:
        app_name = app_map[choice_id]
        emit(dict(event="setup_dispatch", tool="launch_app", arguments={"name": app_name}))
        try:
            result = await driver.call("launch_app", {"name": app_name})
        except Exception as error:
            emit(dict(event="setup_failed", **error_details(error)))
            return "unknown"
            
        pid = result.get("pid")
        if type(pid) is not int or pid <= 0:
            return "unknown"
            
        windows = result.get("windows", [])
        for _ in range(5):
            if select_window(windows, pid) is not None:
                break
            await asyncio.sleep(0.5)
            try:
                windows = (await driver.call("list_windows", {"pid": pid})).get("windows", [])
            except Exception:
                pass
                
        window_id = select_window(windows, pid)
        if window_id is None:
            return "needs_window_selection"
            
        if driver.accepts("bring_to_front", {"pid": pid, "window_id": window_id}):
            try:
                await driver.call("bring_to_front", {"pid": pid, "window_id": window_id})
                await asyncio.sleep(1.2)
            except Exception:
                pass
        return (pid, window_id)

def add_menu_regions(regions, observation, task=None):
    if not observation.menu_paths:
        return
    menu_groups = {}
    EXCLUDE_MENUS = {"Apple", observation.app_name, "Window", "Help"}
    for path in observation.menu_paths:
        if len(path) >= 2 and path[0] not in EXCLUDE_MENUS:
            menu_groups.setdefault(path[0], []).append(path)
    if not menu_groups:
        return
    app_words = set(re.findall(r"\w+", (observation.app_name or "").lower()))
    goal_words = {w for w in re.findall(r"\w+", task.goal.lower()) if w not in MENU_STOPWORDS and w not in app_words} if (task and getattr(task, "goal", None)) else set()
    def menu_score(item):
        top_m, paths = item
        score = 0
        top_m_words = set(re.findall(r"\w+", top_m.lower()))
        if any(w in goal_words for w in top_m_words):
            score += 100
        for p in paths:
            for part in p[1:]:
                part_words = set(re.findall(r"\w+", part.lower()))
                score += sum(10 for w in goal_words if w in part_words)
        # Give core operational editing menus a baseline score so they are accessible
        if top_m in ("Edit", "Insert", "Data", "Track", "Format"):
            score += 5
        return score
    sorted_menus = sorted(menu_groups.items(), key=menu_score, reverse=True)
    # Expose top operational menus (up to 3)
    for top_m, paths in sorted_menus[:3]:
        r_key = f"menu_{top_m.lower()}"
        regions[r_key] = {
            "name": f"{top_m} Menu",
            "menu_name": top_m,
            "elements": [],
            "paths": paths
        }

def get_regions(observation, task=None):
    roots = [e for e in observation.elements if e.parent is None]
    root_idx = roots[0].index if roots else 0
    direct_children = [e for e in observation.elements if e.parent == root_idx or e.parent is None]
    
    # If elements have bounding frames and window frame is available, partition by vertical layout zones
    window_frame = roots[0].frame if roots else None
    if window_frame and window_frame[3] > 0:
        # Compact window (e.g. calculator, small utility): single region
        if window_frame[3] < 500:
            active_elements = [e for e in observation.elements if e.role not in ("AXWindow", "AXMenuBar", "AXMenuBarItem", "AXMenu", "AXMenuItem")]
            regions = {"main": {"name": "Application Controls", "elements": active_elements}}
            add_menu_regions(regions, observation, task)
            return regions
        
        # Standard application window: partition by vertical layout into Toolbar/Controls, Content, and Footer
        # Check if window has a dominant canvas/workspace container (e.g. spreadsheet grid, DAW timeline, canvas)
        canvas_elem = None
        for e in observation.elements:
            if e.role in ("AXWindow", "AXWebArea", "AXMenuBar", "AXMenuBarItem", "AXMenu", "AXMenuItem"):
                continue
            if e.frame and len(e.frame) == 4:
                area = float(e.frame[2]) * float(e.frame[3])
                if area >= 100000:
                    canvas_elem = e
                    break

        if canvas_elem and canvas_elem.frame:
            top_y = canvas_elem.frame[1]
            bot_y = canvas_elem.frame[1] + canvas_elem.frame[3]
            win_top = window_frame[1]
            c_top_rel = max(0.0, float(top_y - win_top))
            c_h = float(canvas_elem.frame[3])
            controls_bounds = (0.0, 0.0, float(window_frame[2]), c_top_rel)
            content_bounds = (0.0, c_top_rel, float(window_frame[2]), c_h)
            footer_bounds = (0.0, c_top_rel + c_h, float(window_frame[2]), max(50.0, float(window_frame[3]) - (c_top_rel + c_h)))
        else:
            top_y = window_frame[1] + 190
            bot_y = window_frame[1] + window_frame[3] - 100
            controls_bounds = (0.0, 0.0, float(window_frame[2]), 190.0)
            content_bounds = (0.0, 190.0, float(window_frame[2]), float(window_frame[3]) - 290.0)
            footer_bounds = (0.0, float(window_frame[3]) - 100.0, float(window_frame[2]), 100.0)

        top_els = []
        mid_els = []
        bot_els = []
        for e in observation.elements:
            if e.role in ("AXWindow", "AXMenuBar", "AXMenuBarItem", "AXMenu", "AXMenuItem"):
                continue
            y = e.frame[1] if e.frame else window_frame[1]
            if y < top_y:
                top_els.append(e)
            elif y >= bot_y:
                bot_els.append(e)
            else:
                mid_els.append(e)
        regions = {}
        if top_els:
            regions["controls"] = {"name": "Header & Main Controls Area", "elements": top_els, "bounds": controls_bounds}
        if mid_els:
            regions["content"] = {"name": "Content & Document Workspace", "elements": mid_els, "bounds": content_bounds}
        if bot_els:
            regions["footer"] = {"name": "Status & Footer Controls", "elements": bot_els, "bounds": footer_bounds}
        if regions:
            add_menu_regions(regions, observation, task)
            return regions

    # Standard hierarchical fallback for deeply nested apps
    children = {}
    for e in observation.elements:
        children.setdefault(e.parent, []).append(e.index)
        
    regions = {}
    if roots:
        root = roots[0]
        region_roots = children.get(root.index, [])
        while len(region_roots) <= 2 and region_roots:
            next_level = []
            for rr in region_roots:
                next_level.extend(children.get(rr, []))
            if not next_level:
                break
            region_roots = next_level
            
        for rr_idx in region_roots:
            rr_el = next((e for e in observation.elements if e.index == rr_idx), None)
            if rr_el:
                label = rr_el.label or rr_el.value or rr_el.role
                regions[str(rr_idx)] = {"name": f"{rr_el.role}: {label}", "elements": [], "element": rr_el}
                
    if not regions:
        regions["main"] = {"name": "Main Window Content", "elements": [], "element": None}
        
    for e in observation.elements:
        curr = e.index
        assigned = False
        while curr is not None:
            if str(curr) in regions:
                regions[str(curr)]["elements"].append(e)
                assigned = True
                break
            el = next((p for p in observation.elements if p.index == curr), None)
            curr = el.parent if el else None
            
        if not assigned:
            target_k = list(regions.keys())[0]
            regions[target_k]["elements"].append(e)
            
    active_regions = {k: v for k, v in regions.items() if len(v["elements"]) > 0}
    add_menu_regions(active_regions, observation, task)
    return active_regions

def summarize_screen(observation, regions, visual_lines=None, visual_texts=None):
    visible_texts = []
    for el in observation.elements:
        for val in (el.value, el.label):
            if val and isinstance(val, str):
                cleaned = val.replace("\u200e", "").replace("\u200f", "").strip()
                if cleaned and len(cleaned) <= 100 and cleaned not in visible_texts:
                    if cleaned != observation.window_title:
                        visible_texts.append(cleaned)
    parts = []
    if observation.window_title and ("*" in observation.window_title or "[unsaved]" in observation.window_title.lower()):
        parts.append("document state: unsaved changes (*)")
    content_reg = regions.get("content") or regions.get("main")
    if content_reg and content_reg.get("elements"):
        c_labels = [e.label or e.value for e in content_reg["elements"] if (e.label or e.value) and e.role in ("AXButton", "AXPopUpButton", "AXRadioButton", "AXCheckBox")]
        c_unique = []
        for l in c_labels:
            lc = str(l).strip()
            if lc and lc not in c_unique and len(lc) <= 50:
                c_unique.append(lc)
        if c_unique:
            parts.append(f"workspace controls: {', '.join(repr(x) for x in c_unique[:6])}")
        else:
            f_labels = [e.label or e.value for e in content_reg["elements"] if (e.label or e.value) and e.role in ("AXTextField", "AXStaticText")]
            f_unique = [str(l).strip() for l in f_labels if str(l).strip() and len(str(l).strip()) <= 50]
            if f_unique:
                parts.append(f"workspace content: {', '.join(repr(x) for x in f_unique[:4])}")
    if visible_texts:
        if len(visible_texts) > 16:
            sampled_texts = visible_texts[:8] + visible_texts[-6:]
        else:
            sampled_texts = visible_texts
        parts.append(f"visible text/readouts: {', '.join(repr(t) for t in sampled_texts)}")
    if visual_lines:
        line_summaries = [l.text for l in visual_lines if l.text not in visible_texts and l.text != observation.window_title]
        if line_summaries:
            parts.append(f"visually detected screen/display text: {', '.join(repr(t) for t in line_summaries[:8])}")
    elif visual_texts:
        unique_vis = [t for t in visual_texts if t not in visible_texts and t != observation.window_title]
        if unique_vis:
            parts.append(f"visually detected screen/display text: {', '.join(repr(t) for t in unique_vis[:8])}")
    region_names = [r["name"].split(" (")[0] for r in regions.values()]
    parts.append(f"regions: {', '.join(region_names)}")
    return f"Window '{observation.window_title}' ({observation.app_name}): " + "; ".join(parts) + "."

async def observe_visual_regions(driver, observation, emit, force_look_closely=False, last_capture_id=None, cached_lines=None, cached_texts=None):
    parsed_regions = []
    # 1. Optical parse from cua-perception if available
    has_dominant_canvas = any(
        getattr(e, "role", "") == "AXUnknown" and getattr(e, "frame", (0, 0, 0, 0))[2] > 400 and getattr(e, "frame", (0, 0, 0, 0))[3] > 200
        for e in getattr(observation, "elements", ())
    )
    should_run, use_cached = should_trigger_adaptive_perception(
        observation,
        has_dominant_canvas=has_dominant_canvas,
        force_look_closely=force_look_closely,
        last_capture_id=last_capture_id
    )

    if (should_run or force_look_closely) and observation.capture_id and driver.accepts("parse_visual_regions", {"capture_id": observation.capture_id}):
        try:
            res = await driver.call(
                "parse_visual_regions",
                {
                    "capture_id": observation.capture_id,
                    "options": {"kinds": ["text", "icon"], "min_confidence": 0.5, "max_regions": 250},
                },
            )
            if isinstance(res, dict) and "regions" in res:
                raw_regs = res.get("regions", [])
                emit(dict(event="visual_regions_observed", count=len(raw_regs)))
                parsed_regions = parse_raw_regions(raw_regs, min_confidence=0.5)
        except Exception as e:
            emit(dict(event="visual_regions_unavailable", reason=str(e)))

    # Window bounds for line clustering
    w_width = 800.0
    w_height = 600.0
    for e in getattr(observation, "elements", ()):
        if getattr(e, "parent", None) is None and getattr(e, "frame", None):
            w_width = float(e.frame[2])
            w_height = float(e.frame[3])
            break

    if parsed_regions:
        visual_lines = cluster_into_lines(parsed_regions, w_width, w_height)
        visual_texts = []
        for line in visual_lines:
            if line.text and line.text not in visual_texts:
                visual_texts.append(line.text)
    else:
        visual_lines = cached_lines or []
        visual_texts = cached_texts or []

    if observation.readback_text:
        for m in re.finditer(r'AXStaticText\s*=\s*"([^"]+)"', observation.readback_text):
            val = m.group(1).replace("\u200e", "").replace("\u200f", "").strip()
            if val and val not in visual_texts:
                visual_texts.append(val)

    return parsed_regions, visual_lines, visual_texts

async def step_1_and_2_loop(task, driver, chooser, emit, target, dry_run=False, max_steps=24, minimum_confidence=0.1, history=None, worked=None, did_not_work=None, entered_records=None):
    from native_candidates import build_native_candidates
    history = history if history is not None else []
    worked = worked if worked is not None else []
    did_not_work = did_not_work if did_not_work is not None else []
    entered_records = entered_records if entered_records is not None else []
    action_taken = False
    consecutive_reobserve = 0
    last_exited_region = None

    cached_visual_regions = None
    cached_visual_lines = None
    cached_visual_texts = None
    last_cid = None
    force_look_closely = False
    just_looked_closely = False

    for step in range(max_steps):
        observation = await driver.observe(*target)
        emit(dict(event="observation", snapshot_id=observation.id))
        
        parsed_regions, visual_lines, visual_texts = await observe_visual_regions(
            driver,
            observation,
            emit,
            force_look_closely=force_look_closely,
            last_capture_id=last_cid,
            cached_lines=cached_visual_lines,
            cached_texts=cached_visual_texts
        )
        if visual_lines:
            cached_visual_lines = visual_lines
        if visual_texts:
            cached_visual_texts = visual_texts
        if parsed_regions:
            just_looked_closely = True
        last_cid = observation.capture_id
        force_look_closely = False
        
        if verify(task, observation):
            return "verified"

        candidates_obj = build_native_candidates(task, observation, driver.accepts, read_only=False)
        candidates = {c.id: c for c in candidates_obj.candidates}
        
        regions = get_regions(observation, task=task)
        region_criteria = {}
        for idx, r in regions.items():
            if "menu_name" in r:
                menu_name = r["menu_name"]
                actionable = sum(1 for c in candidates.values() if c.tool == "invoke_menu" and c.arguments.get("path", [None])[0] == menu_name)
                if actionable > 0:
                    goal_words = {w for w in re.findall(r"\w+", task.goal.lower()) if w not in MENU_STOPWORDS} if (task and getattr(task, "goal", None)) else set()
                    def path_relevance(p):
                        words = set(re.findall(r"\w+", " ".join(p).lower()))
                        return sum(1 for w in goal_words if w in words)
                    sorted_paths = sorted(r.get("paths", []), key=path_relevance, reverse=True)
                    sample_items = [p[-1] for p in sorted_paths[:3]]
                    sample_str = f": {', '.join(sample_items)}" if sample_items else ""
                    region_criteria[f"r_{idx}"] = f"{r['name']}{sample_str} ({actionable} menu commands)"
            else:
                actionable = sum(1 for e in r["elements"] if any(c.id.startswith(f"click-{e.index}") or c.id.startswith(f"type-{e.index}") for c in candidates.values()))
                if idx == "content" and task.inputs:
                    actionable += len(task.inputs)
                if actionable > 0:
                    has_canvas = any(
                        e.role in ("AXImage", "AXUnknown", "AXWebArea", "AXGroup") and
                        e.frame and len(e.frame) == 4 and float(e.frame[2]) * float(e.frame[3]) >= 80000
                        for e in r["elements"]
                    )
                    labels = [e.label or e.value for e in r["elements"] if (e.label or e.value) and e.role in ("AXButton", "AXTextField", "AXPopUpButton", "AXRadioButton", "AXCheckBox")]
                    unique_labels = []
                    for l in labels:
                        l_clean = str(l).strip()
                        if l_clean and l_clean not in unique_labels:
                            unique_labels.append(l_clean)
                    if has_canvas:
                        sample_labels = ["Spreadsheet grid canvas", "active cells"] + unique_labels[:2]
                    elif len(unique_labels) <= 6:
                        sample_labels = unique_labels
                    else:
                        sample_labels = unique_labels[:4] + unique_labels[-2:]
                    label_str = f": {', '.join(repr(x) for x in sample_labels)}" if sample_labels else ""
                    desc = f"{r['name']}{label_str} ({actionable} actionable controls)"
                    if last_exited_region == f"r_{idx}":
                        desc = f"{desc} (just exited; select a different region or action)"
                    region_criteria[f"r_{idx}"] = desc
            
        if not just_looked_closely:
            region_criteria["look_closely"] = "Look closely: run optical vision parse to inspect custom canvas or canvas pixels"
        success_summary = "; ".join(task.brief.get("success", [])) if (task.brief and "success" in task.brief) else "All task requirements"
        region_criteria["done"] = f"The goal is visibly achieved and all success criteria are met ({success_summary}); hand off for review"
        if consecutive_reobserve >= 1:
            region_criteria["reobserve"] = "Re-read the whole window before deciding (window was already freshly observed; if required values and tabs are visibly present, select 'done' instead of re-reading again)"
        else:
            region_criteria["reobserve"] = "Re-read the whole window before deciding"
        region_criteria["switch_app"] = "This window cannot achieve the goal; choose a different app or window"
        
        app_desc = get_app_descriptor(observation.app_name)
        screen_summary = summarize_screen(observation, regions, visual_lines=visual_lines, visual_texts=visual_texts)
        step1_state = {
            "goal": format_goal(task.goal),
            "app": f"{observation.app_name} window '{observation.window_title}' ({app_desc})",
            "screen": screen_summary,
            "worked": worked[-5:],
            "did_not_work": did_not_work[-5:]
        }
        if visual_lines:
            step1_state["visual_readouts"] = format_visual_lines_for_prompt(visual_lines, max_lines=40, max_bytes=3500)
        elif visual_texts:
            step1_state["visual_readouts"] = visual_texts[:8]
        if task.brief:
            if "required_sequence" in task.brief:
                # Dynamic workflow phase progress tracking as specified in schema_v2.md & SKILL.md
                # Determine progress against sequence steps
                seq = task.brief["required_sequence"]
                workflow_status = []
                # Check whether navigation / document open phase has been reached
                has_doc_loaded = bool(observation.window_title and observation.window_title != "Untitled" and "Google Sheets" in observation.window_title)
                entered_texts = {r["text"] for r in entered_records}
                all_obs_text = (" ".join(visual_texts) + " " + " ".join(e.label or e.value or "" for e in observation.elements)).lower()
                
                for s_idx, step_desc in enumerate(seq):
                    is_completed = False
                    
                    if s_idx == 0 and "navigate" in step_desc.lower():
                        # Completed if the document title/URL shows target loaded or navigation succeeded
                        if has_doc_loaded or (task.inputs and task.inputs[0] in entered_texts):
                            is_completed = True
                    else:
                        # Check if task inputs referenced in this step description have been entered or are visibly observed
                        step_inputs = [inp for inp in task.inputs if inp.lower() in step_desc.lower()]
                        if step_inputs and all((inp in entered_texts or inp.lower() in all_obs_text) for inp in step_inputs):
                            is_completed = True
                    
                    if is_completed:
                        workflow_status.append(f"[COMPLETED] {step_desc}")
                    else:
                        # First uncompleted step is current active phase
                        if not any("[ACTIVE]" in s for s in workflow_status):
                            workflow_status.append(f"[ACTIVE] {step_desc}")
                        else:
                            workflow_status.append(f"[PENDING] {step_desc}")
                
                step1_state["workflow"] = workflow_status
            if "success" in task.brief:
                step1_state["success_criteria"] = task.brief["success"]
        if entered_records:
            step1_state["entered"] = [r["desc"] for r in entered_records[-8:]]
        if history and action_taken:
            step1_state["last_action"] = history[-1]["description"]
            step1_state["action_history"] = [h["description"] for h in history[-12:]]
            
        request_step1 = {
            "state": step1_state,
            "questions": {
                "region": {
                    "type": "choice",
                    "instructions": "Which area of the window should be examined for the next action? Review both accessibility controls and visual screen readouts to locate your target. If an area contains custom canvases or unlabelled AXUnknown surfaces, choose 'look_closely' to inspect rendered visual content. Select 'done' only when all required values and success criteria are visibly confirmed in the visual readouts.",
                    "criteria": region_criteria
                }
            }
        }
        
        if history and action_taken:
            request_step1["questions"]["last_action"] = {
                "type": "choice",
                "instructions": "Judging from the current screen and visual readouts, did the most recent action advance the task? Page navigation, document loading, active text entry, cursor movement, selection change, or new values all count as 'advanced'. Only choose 'no_effect' if the screen, active cursor, and values remain completely unchanged.",
                "criteria": {
                    "advanced": "Yes: page navigated, document loaded, active text entry, cursor movement, selection change, or new values appeared",
                    "no_effect": "Nothing changed: screen, active position, and selection remain identical to before",
                    "set_back": "It moved away from the goal or opened something unrelated",
                    "unclear": "The screen does not show enough to tell"
                }
            }
            
        emit(dict(event="v2_step_1_request", request=request_step1))
        if dry_run:
            return "dry_run"
            
        response1 = await choose_v2(chooser, request_step1)
        
        last_action_eval = None
        if "last_action" in response1.choices:
            eval_choice = response1.choices["last_action"].choice
            last_action_eval = eval_choice
            last_action_desc = history[-1]["description"]
            if eval_choice == "advanced":
                worked.append(f"{last_action_desc}: advanced toward goal")
            elif eval_choice == "unclear":
                did_not_work.append(f"{last_action_desc} (unclear)")
            else:
                did_not_work.append(f"{last_action_desc} ({eval_choice})")
                
        region_choice = response1.choices["region"].choice
        emit(dict(event="v2_step_1_decision", choice=region_choice, last_action_eval=last_action_eval))
        
        if region_choice == "done":
            return "review_required"
        elif region_choice == "reobserve":
            consecutive_reobserve += 1
            force_look_closely = True
            await asyncio.sleep(0.5)
            continue
        elif region_choice == "look_closely":
            consecutive_reobserve = 0
            force_look_closely = True
            await asyncio.sleep(0.2)
            continue
        elif region_choice == "switch_app":
            return "switch_app"
            
        consecutive_reobserve = 0
        # Step 2: Action in region
        region_key = region_choice.removeprefix("r_")
        selected_region = regions.get(region_key, list(regions.values())[0])

        # Ensure entry fields that accept typing have input candidates if task specifies inputs
        for e in selected_region["elements"]:
            e_val = (e.value or e.label or "").strip()
            is_entry_surface = e.role in ("AXTextField", "AXTextArea")
            if e.token and is_entry_surface:
                for inp_idx, inp_val in enumerate(task.inputs):
                    if inp_val and inp_val == e_val:
                        continue
                    type_c_id = f"type-{e.index}-{inp_idx}"
                    if type_c_id not in candidates:
                        type_args = {"pid": observation.pid, "window_id": observation.window_id,
                                     "element_token": e.token, "text": inp_val}
                        if driver.accepts("type_text", type_args):
                            target_name = e.label or f"{e.role} (element {e.index})"
                            is_entered = any(r["text"] == inp_val for r in entered_records)
                            tag = " [already entered]" if is_entered else ""
                            c_desc = f"Type {inp_val!r} into {target_name}{tag}"
                            candidates[type_c_id] = Candidate(type_c_id, c_desc, "type_text", type_args)
        
        action_criteria = {}
        if "menu_name" in selected_region:
            menu_name = selected_region["menu_name"]
            matching_cands = [c for c in candidates.values() if c.tool == "invoke_menu" and c.arguments.get("path", [None])[0] == menu_name]
            goal_words = {w for w in re.findall(r"\w+", task.goal.lower()) if w not in MENU_STOPWORDS} if (task and getattr(task, "goal", None)) else set()
            CORE_EDIT_ITEMS = {"Undo", "Redo", "Cut", "Copy", "Paste", "Paste Special…", "Fill Down", "Fill Right", "AutoFill", "Flash Fill"}
            def item_score(c):
                p = c.arguments.get("path", [])
                score = 0
                for part in p[1:]:
                    part_clean = part.replace("…", "").strip()
                    part_words = set(re.findall(r"\w+", part_clean.lower()))
                    score += sum(10 for w in goal_words if w in part_words)
                    if part_clean in CORE_EDIT_ITEMS:
                        score += 5
                return score
            sorted_matching = sorted(matching_cands, key=item_score, reverse=True)
            for c in sorted_matching[:8]:
                action_criteria[c.id] = c.description
        else:
            RELEVANT_KEYS = {
                "return": "Press Return (submit input/URL, activate default action, or commit entry)",
                "tab": "Press Tab (advance focus to next field/control, or move right in grid)",
                "escape": "Press Escape (dismiss autocomplete popup/suggestions, or cancel editing)",
                "left": "Press Left arrow (move cursor or navigate left)",
                "right": "Press Right arrow (move cursor or navigate right)",
                "up": "Press Up arrow (move cursor or navigate up)",
                "down": "Press Down arrow (move cursor or navigate down)",
                "backspace": "Press Backspace (delete character or clear selection)",
            }
            for raw_k, k_desc in RELEVANT_KEYS.items():
                candidate_id = None
                if f"key-{raw_k}-foreground" in candidates:
                    candidate_id = f"key-{raw_k}-foreground"
                elif f"key-{raw_k}" in candidates:
                    candidate_id = f"key-{raw_k}"
                if candidate_id:
                    action_criteria[candidate_id] = k_desc

            RELEVANT_HOTKEYS = {
                "hotkey-cmd-l": "Focus address and search bar (Cmd+L)",
                "hotkey-cmd-a": "Select all content or elements (Cmd+A)",
                "hotkey-cmd-c": "Copy current selection to clipboard (Cmd+C)",
                "hotkey-cmd-v": "Paste clipboard content at cursor or into selection (Cmd+V)",
                "hotkey-cmd-z": "Undo previous action (Cmd+Z)",
                "hotkey-shift-down": "Extend selection down to include item below (Shift+Down)",
                "hotkey-shift-up": "Extend selection up to include item above (Shift+Up)",
                "hotkey-cmd-shift-down": "Extend selection down to the block or table boundary (Cmd+Shift+Down)",
                "hotkey-cmd-shift-right": "Extend selection right to the block or row boundary (Cmd+Shift+Right)",
                "hotkey-cmd-d": "Fill down formula/value or bookmark page (Cmd+D)",
            }
            for hk_id, hk_desc in RELEVANT_HOTKEYS.items():
                if f"{hk_id}-foreground" in candidates:
                    action_criteria[f"{hk_id}-foreground"] = hk_desc
                elif hk_id in candidates:
                    action_criteria[hk_id] = hk_desc

            # In accordance with driver_candidates.py contract, typing requires an observed field target.
            # Window activation alone does not establish the receiving control.
            # Explicit target fields (AXTextField, AXTextArea, etc.) compiled by build_native_candidates
            # provide targeted typing options. Blind un-targeted typing candidates are not generated.

            # Offer visual coordinate clicks for rendered text/icons in the selected region
            if parsed_regions:
                reg_bounds = selected_region.get("bounds")
                vis_cands = build_visual_click_candidates(
                    parsed_regions,
                    observation,
                    driver.accepts,
                    candidates,
                    region_bounds=reg_bounds,
                    max_candidates=35
                )
                for vc in vis_cands:
                    candidates[vc.id] = vc
                    action_criteria[vc.id] = vc.description

            for e in selected_region["elements"]:
                # Never offer unlabelled window control buttons (1, 2, 3) as task actions
                if e.index in (1, 2, 3) and e.role == "AXButton" and not (e.label or "").strip():
                    continue
                # Do not offer destructive tab-close buttons embedded inside tabs
                if e.role == "AXButton" and e.label == "Close" and getattr(e, "parent", None) is not None:
                    parent_el = next((p for p in observation.elements if p.index == e.parent), None)
                    if parent_el and parent_el.role == "AXRadioButton":
                        continue

                e_val = (e.value or "").strip()
                # Check if this element is a persistent locator control (e.g. Name Box next to range menu button)
                is_locator = False
                if e.frame and len(e.frame) == 4:
                    for other in observation.elements:
                        o_lbl = (other.label or "").lower()
                        if other.frame and len(other.frame) == 4 and "name box" in o_lbl:
                            if abs(other.frame[1] - e.frame[1]) < 10 and abs(other.frame[0] - (e.frame[0] + e.frame[2])) < 20:
                                is_locator = True
                                break

                # Clean candidate selection per element to ensure budget compliance (under 40,000 bytes)
                # 1. Prefer direct click; if absent, use direct foreground area click
                if is_locator and e.label:
                    if f"click-{e.index}" in candidates:
                        action_criteria[f"click-{e.index}"] = candidates[f"click-{e.index}"].description.replace(f"'{e.label}'", f"'{e.label}' (Name box locator in toolbar)")
                else:
                    if "address" in (e.label or "").lower() and f"click-{e.index}-area-{e.index}-foreground" in candidates:
                        action_criteria[f"click-{e.index}-area-{e.index}-foreground"] = candidates[f"click-{e.index}-area-{e.index}-foreground"].description
                    elif f"click-{e.index}" in candidates:
                        action_criteria[f"click-{e.index}"] = candidates[f"click-{e.index}"].description
                    elif f"click-{e.index}-area-{e.index}-foreground" in candidates:
                        action_criteria[f"click-{e.index}-area-{e.index}-foreground"] = candidates[f"click-{e.index}-area-{e.index}-foreground"].description

                # 2. Contextual actions (double_click on tabs/cells, right_click on items)
                if e.role in ("AXPopUpButton", "AXTab", "AXRow", "AXCell", "AXTextField", "AXTextArea", "AXLink", "AXUnknown"):
                    lbl = (e.label or e.value or "").strip()
                    name_str = f"'{lbl}'" if lbl else f"(id {e.index})"
                    if f"double_click-{e.index}" in candidates:
                        action_criteria[f"double_click-{e.index}"] = f"Double-click {e.role} {name_str} (element {e.index}) to edit, rename, or open inline."
                    if f"right_click-{e.index}" in candidates:
                        action_criteria[f"right_click-{e.index}"] = f"Right-click {e.role} {name_str} (element {e.index}) to open its context menu (e.g. rename, duplicate, delete)."

                # 3. Explicit advertised actions (show_menu, pick, etc.)
                for act in ("show_menu", "pick", "confirm", "cancel", "open"):
                    act_id = f"action-{e.index}-{act}"
                    if act_id in candidates:
                        action_criteria[act_id] = candidates[act_id].description

                # 4. Input typing candidates for text fields and editable controls (e.g. tabs)
                if e.role in ("AXTextField", "AXTextArea", "AXSearchField", "AXComboBox", "AXPopUpButton", "AXTab"):
                    for inp_idx, inp_val in enumerate(task.inputs):
                        type_c_id = f"type-{e.index}-{inp_idx}"
                        if type_c_id not in candidates and getattr(e, "token", None):
                            type_args = {
                                "pid": observation.pid, "window_id": observation.window_id,
                                "element_token": e.token, "text": inp_val, "delivery_mode": "foreground"
                            }
                            if driver.accepts("type_text", type_args):
                                c_desc = f"Type supplied text {inp_val!r} into {e.role} '{e.label or e.value}' (element {e.index})."
                                candidates[type_c_id] = Candidate(type_c_id, c_desc, "type_text", type_args)
                        if type_c_id in candidates:
                            desc = candidates[type_c_id].description
                            if is_locator and e.label:
                                desc = desc.replace(f"'{e.label}'", f"'{e.label}' (Name box locator in toolbar)")
                            if task.brief and "input_purposes" in task.brief:
                                purposes = task.brief["input_purposes"]
                                targets = task.brief.get("input_targets", [])
                                if inp_idx < len(purposes):
                                    t_hint = targets[inp_idx] if inp_idx < len(targets) else ""
                                    e_name = (e.label or e.value or "").strip().lower()
                                    # Do not attach cell-specific data entry purpose to a persistent locator control
                                    if is_locator and t_hint and t_hint.lower() not in ("name_box", "locator", "address"):
                                        pass
                                    elif not t_hint or t_hint.lower() in e_name or e_name in t_hint.lower() or (t_hint.lower() in ("sheet_tab_name", "tab") and e.role in ("AXPopUpButton", "AXTab")):
                                        desc = f"{desc} (Purpose: {purposes[inp_idx]})"
                            action_criteria[type_c_id] = desc

            # If the selected region contains a document canvas container without discrete accessible text fields,
            # offer canvas text entry targeting the active canvas position
            canvas_target = None
            for el in selected_region["elements"]:
                if el.role in ("AXImage", "AXUnknown", "AXWebArea", "AXGroup", "AXScrollArea"):
                    if el.frame and len(el.frame) == 4 and float(el.frame[2]) * float(el.frame[3]) >= 80000:
                        canvas_target = el
                        break

            if canvas_target and task.inputs:
                c_token = getattr(canvas_target, "token", None)
                for inp_idx, inp_val in enumerate(task.inputs):
                    t_args = {
                        "pid": observation.pid,
                        "window_id": observation.window_id,
                        "text": inp_val,
                        "delivery_mode": "foreground"
                    }
                    if c_token:
                        t_args["element_token"] = c_token
                    if driver.accepts("type_text", t_args):
                        c_id = f"type-canvas-{inp_idx}"
                        desc = f"Type supplied text {inp_val!r} at the active cursor/cell position in {selected_region['name']} canvas."
                        if task.brief and "input_purposes" in task.brief:
                            purposes = task.brief["input_purposes"]
                            targets = task.brief.get("input_targets", [])
                            if inp_idx < len(purposes):
                                t_hint = targets[inp_idx] if inp_idx < len(targets) else ""
                                if not t_hint or t_hint.lower() not in ("address_bar", "sheet_tab_name"):
                                    desc = f"{desc} (Purpose: {purposes[inp_idx]})"
                        candidates[c_id] = Candidate(c_id, desc, "type_text", t_args)
                        action_criteria[c_id] = desc
                        
        success_summary = "; ".join(task.brief.get("success", [])) if (task.brief and "success" in task.brief) else "All task requirements"
        action_criteria["done"] = f"The goal is visibly achieved and all success criteria are met ({success_summary}); hand off for review"
        if not just_looked_closely:
            action_criteria["look_closely"] = "Look closely: re-scan the visual screen and canvas values to verify progress or detect visual controls"
        action_criteria["regions"] = "None of these fit; go back to the region list"

        # Annotate actions that recently had no effect to prevent repetitive loops
        for act_id, act_desc in list(action_criteria.items()):
            if act_id in ("done", "look_closely", "regions"):
                continue
            for dnw in did_not_work[-5:]:
                if "no_effect" in dnw:
                    act_parts = act_id.split("-")
                    el_id = act_parts[-1] if (act_parts and act_parts[-1].isdigit()) else None
                    if act_desc in dnw or (el_id and f"element {el_id}" in dnw):
                        action_criteria[act_id] = f"{act_desc} (previously attempted; had no effect)"
                        break

        # Strictly enforce TypeSafe SystemOne criteria limit (maximum 255 items; cap at 200 to guarantee compliance)
        if len(action_criteria) > 200:
            preserved_keys = [k for k in ("done", "look_closely", "regions") if k in action_criteria]
            essential_keys = [k for k in action_criteria if k.startswith("type-") or k.startswith("hotkey-") or k.startswith("key-")]
            other_keys = [k for k in action_criteria if k not in preserved_keys and k not in essential_keys]
            budget_for_others = 200 - len(preserved_keys) - len(essential_keys)
            if budget_for_others > 0:
                retained_keys = set(preserved_keys + essential_keys + other_keys[:budget_for_others])
            else:
                retained_keys = set(preserved_keys + essential_keys[:195])
            action_criteria = {k: v for k, v in action_criteria.items() if k in retained_keys}

        if "menu_name" in selected_region:
            region_items = [f"{' > '.join(p)}" for p in selected_region.get("paths", [])[:6]]
            region_detail_str = f"{selected_region['name']}: {', '.join(region_items)}."
        else:
            region_items = []
            for el in selected_region["elements"][:8]:
                val = (el.value or "").strip()
                lbl = (el.label or "").strip()
                item = el.role
                if lbl and val and lbl != val:
                    item += f" '{lbl}'={val!r}"
                elif val:
                    item += f" val={val!r}"
                elif lbl:
                    item += f" '{lbl}'"
                region_items.append(f"{item} (id {el.index})")
            region_detail_str = f"{selected_region['name']}: {', '.join(region_items)}."

        step2_state = {
            "goal": format_goal(task.goal),
            "app": f"{observation.app_name} window '{observation.window_title}' ({app_desc})",
            "screen": screen_summary,
            "region": selected_region["name"],
            "region_detail": region_detail_str,
            "worked": worked[-5:],
            "did_not_work": did_not_work[-5:]
        }
        if visual_lines:
            step2_state["visual_readouts"] = format_visual_lines_for_prompt(visual_lines, max_lines=40, max_bytes=3500)
        elif visual_texts:
            step2_state["visual_readouts"] = visual_texts[:8]
        if task.brief:
            if "required_sequence" in task.brief:
                step2_state["workflow"] = workflow_status
            if "success" in task.brief:
                step2_state["success_criteria"] = task.brief["success"]
        if entered_records:
            step2_state["entered"] = [r["desc"] for r in entered_records[-8:]]
        if history:
            step2_state["last_action"] = history[-1]["description"]
            step2_state["action_history"] = [h["description"] for h in history[-12:]]
        
        request_step2 = {
            "state": step2_state,
            "questions": {
                "next_action": {
                    "type": "choice",
                    "instructions": "Pick the single next action in this area that best advances the goal. To enter data or formulas into a document or spreadsheet canvas, ensure the receiving cell or field is actively focused before typing. If you are unsure of the visual layout or encounter an unlabelled AXUnknown surface, select 'look_closely' to inspect optical text and coordinates. If the desired next action is in another part of the window (e.g. document canvas, toolbar, or menu), select 'regions' to navigate to that region. Consult visual readouts to confirm values rendered inside custom canvases and verify your progress. Do NOT select 'done' until all success criteria numbers and values are visibly present in the visual readouts.",
                    "criteria": action_criteria
                }
            }
        }
        
        emit(dict(event="v2_step_2_request", request=request_step2))
        response2 = await choose_v2(chooser, request_step2)
        action_choice = response2.choices["next_action"].choice
        emit(dict(event="v2_step_2_decision", choice=action_choice))
        
        if action_choice == "done":
            return "review_required"
        elif action_choice == "look_closely":
            force_look_closely = True
            action_taken = False
            continue
        elif action_choice == "regions":
            action_taken = False
            last_exited_region = region_choice
            continue
            
        last_exited_region = None
        candidate = candidates[action_choice]
        clean_desc = action_criteria.get(action_choice, candidate.description)
        history_entry = {
            "description": clean_desc,
            "tool": candidate.tool
        }
        if candidate.arguments:
            if "text" in candidate.arguments:
                history_entry["text"] = candidate.arguments["text"]
            elif "value" in candidate.arguments:
                history_entry["text"] = candidate.arguments["value"]
            if "key" in candidate.arguments:
                history_entry["key"] = candidate.arguments["key"]
        history.append(history_entry)
        
        if candidate.tool:
            action_taken = True
            just_looked_closely = False
            try:
                emit(dict(event="dispatch", tool=candidate.tool, arguments=thaw(candidate.arguments)))
                result = await driver.call(candidate.tool, thaw(candidate.arguments))
                emit(dict(event="tool_result", tool=candidate.tool, result=result))

                # Automatic foreground ladder escalation if background synthetic events report delivery failure
                if isinstance(result, dict) and result.get("escalation", {}).get("target") == "foreground":
                    fg_args = {**candidate.arguments, "delivery_mode": "foreground"}
                    if driver.accepts(candidate.tool, fg_args):
                        emit(dict(event="dispatch_escalation", tool=candidate.tool, arguments=thaw(fg_args)))
                        result = await driver.call(candidate.tool, thaw(fg_args))
                        emit(dict(event="tool_result_escalated", tool=candidate.tool, result=result))

                if candidate.tool == "type_text" and "text" in candidate.arguments:
                    typed_txt = candidate.arguments["text"]
                    purpose_str = ""
                    if task.brief and "input_purposes" in task.brief:
                        try:
                            # Matches type-<element_index>-<input_idx> or type-<input_idx>
                            parts = action_choice.split("-")
                            if parts and parts[-1].isdigit():
                                idx = int(parts[-1])
                                if idx < len(task.brief["input_purposes"]):
                                    purpose_str = f" ({task.brief['input_purposes'][idx]})"
                        except (ValueError, TypeError, IndexError):
                            pass
                    entered_records.append({
                        "text": typed_txt,
                        "desc": f"{typed_txt!r}{purpose_str}"
                    })
            except Exception as error:
                emit(dict(event="action_failed", **error_details(error)))
                # If typing partially succeeded or was delivered, ensure it is preserved in entered_records
                if candidate.tool == "type_text" and "text" in candidate.arguments:
                    typed_txt = candidate.arguments["text"]
                    if not any(r["text"] == typed_txt for r in entered_records):
                        purpose_str = ""
                        if task.brief and "input_purposes" in task.brief:
                            try:
                                parts = action_choice.split("-")
                                if parts and parts[-1].isdigit():
                                    idx = int(parts[-1])
                                    if idx < len(task.brief["input_purposes"]):
                                        purpose_str = f" ({task.brief['input_purposes'][idx]})"
                            except (ValueError, TypeError, IndexError):
                                pass
                        entered_records.append({
                            "text": typed_txt,
                            "desc": f"{typed_txt!r}{purpose_str}"
                        })
                
    return "budget_exhausted"

async def run_loop_v2(task, driver, chooser, emit, *, max_steps=24,
                   no_progress_limit=3, minimum_confidence=.1, seed=0, dry_run=False):
    current_target = None
    persistent_history = []
    persistent_worked = []
    persistent_did_not_work = []
    persistent_entered = []
    
    while True:
        target = await step_0_app_choice(task, driver, chooser, emit, dry_run, current_target=current_target)
        if isinstance(target, str):
            if target == "needs_window_selection":
                continue
            return target
            
        current_target = target
        emit(dict(event="target_bound", pid=target[0], window_id=target[1]))
        
        result = await step_1_and_2_loop(
            task, driver, chooser, emit, target, dry_run, max_steps, minimum_confidence,
            history=persistent_history,
            worked=persistent_worked,
            did_not_work=persistent_did_not_work,
            entered_records=persistent_entered
        )
        if result != "switch_app":
            return result
