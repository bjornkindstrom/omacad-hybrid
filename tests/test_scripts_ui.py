"""Scripts in the window: the folder watcher test-runs AI-written scripts in a separate process and writes
<script>.check.txt, the values panel, running a script (trust, one undo step, rollback), and New Script with AI
(agent start in the scripts folder, or the instructions on the clipboard)."""
import time
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QMessageBox

from omacad.scripting import folder as sfolder
from omacad.scripting.loader import read_info
from omacad.ui.settings import get_settings


@pytest.fixture(scope="module")
def win():
    QApplication.instance() or QApplication([])
    from omacad.ui.main_window import MainWindow
    return MainWindow()


@pytest.fixture
def folder(tmp_path, win):
    get_settings().set("scripts_folder", str(tmp_path / "scripts"))
    win.doc.restore(type(win.doc)().snapshot())
    win.doc.undo_stack.clear()
    return win.scripts_folder()


def _wait(cond, seconds=120):
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.05)
    return False


def test_scripts_commands_are_in_the_ribbon_and_menu(win, monkeypatch):
    assert {"scripts", "new_script_ai", "open_scripts_folder"} <= set(win.command_actions)
    got = []
    monkeypatch.setattr(win, "prompt_new_script_ai", lambda: got.append("ai"))
    monkeypatch.setattr(win, "show_scripts", lambda: got.append("run"))
    win.command_actions["new_script_ai"].trigger()
    win.command_actions["scripts"].trigger()
    assert got == ["ai", "run"]


def test_folder_gets_the_example(folder):
    assert (folder / "gear_generator.py").exists()


def test_watcher_tests_a_saved_script_once_armed(win, folder):
    watcher = win.script_watcher
    results = []
    watcher.checked.connect(lambda p, ok, rep: results.append((Path(p).name, ok, rep)))
    (folder / "before.py").write_text("def run(ctx, params): ctx.box(1, 1, 1)\n", encoding="utf-8")
    watcher.arm()
    time.sleep(1.1)                              # later than armed_since, as a script the AI saves afterwards
    (folder / "plate.py").write_text("NAME = 'Plate'\ndef run(ctx, params):\n    ctx.box(10, 20, 2)\n", encoding="utf-8")
    assert _wait(lambda: any(r[0] == "plate.py" for r in results)), "no test run"
    name, ok, report = next(r for r in results if r[0] == "plate.py")
    assert ok and "volume 400.000 mm3" in report
    assert (folder / "plate.check.txt").read_text(encoding="utf-8") == report
    assert not any(r[0] == "before.py" for r in results)          # files from before arming are not run
    assert win.status_label.text().startswith("plate.py: test OK")
    (folder / "plate.py").write_text("def run(ctx, params):\n    ctx.box(-1, 2, 2)\n", encoding="utf-8")
    assert _wait(lambda: sum(r[0] == "plate.py" for r in results) == 2)
    assert not results[-1][1] and "line 2: length must be larger than 0" in results[-1][2]
    assert "test failed" in win.status_label.text()


def test_params_panel_shows_and_returns_every_value(win):
    from omacad.ui.scripts_ui import ScriptParamsDialog
    info = read_info(sfolder.EXAMPLES / "gear_generator.py")
    dlg = ScriptParamsDialog(info, {"teeth": 33, "hub": True, "pressure_angle": 25.0}, win)
    v = dlg.values()
    assert v["teeth"] == 33 and v["hub"] is True and v["pressure_angle"] == 25.0 and v["module"] == 2.0
    dlg.fields["teeth"][1].setValue(500)                             # the field keeps max
    assert dlg.values()["teeth"] == 150
    dlg.deleteLater()


def test_running_asks_trust_once_and_is_one_undo_step(win, folder, monkeypatch):
    asked = []
    monkeypatch.setattr(QMessageBox, "exec", lambda box: asked.append(box.windowTitle()) or 0)
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box.buttons()[0])     # "Run"
    gear = folder / "gear_generator.py"
    assert win.run_user_script(gear, {"teeth": 12, "module": 1, "thickness": 3, "bore": 2})
    assert asked == ["Run this script?"] and len(win.doc.bodies) == 1
    assert win.doc.undo_label() == "Script: Gear generator"
    assert "Script “Gear generator” done" in win.status_label.text()
    assert win.run_user_script(gear, {"teeth": 13, "module": 1, "thickness": 3, "bore": 0})
    assert asked == ["Run this script?"] and len(win.doc.bodies) == 2   # same content: not asked again
    saved = get_settings().get("script_values")[str(gear.resolve())]
    assert saved["teeth"] == 13


def test_a_failing_script_shows_the_error_and_changes_nothing(win, folder, monkeypatch):
    bad = folder / "bad.py"
    bad.write_text("def run(ctx, params):\n    ctx.box(5, 5, 5)\n    raise ValueError('too wide')\n", encoding="utf-8")
    get_settings().set("trusted_scripts", sfolder.trust({}, bad))
    shown = []
    monkeypatch.setattr(win, "_show_script_error", lambda name, path, report, short: shown.append(short))
    before = win.doc.snapshot()
    assert not win.run_user_script(bad, {})
    assert shown == ["line 3: ValueError: too wide\n    raise ValueError('too wide')"]
    assert win.doc.snapshot() == before


def test_new_script_with_ai_starts_the_agent_in_the_scripts_folder(win, folder, monkeypatch):
    from omacad import feedback
    from omacad.ui import scripts_ui
    started = []
    monkeypatch.setattr(win, "_agent_name", lambda: "Claude Code")
    monkeypatch.setattr(feedback, "launch_agent_text", lambda text, cwd, choice=None: started.append((text, cwd)) or True)

    def fake_exec(dlg):
        dlg.edt_wish.setPlainText("A gear rack with adjustable tooth count")
        dlg._done("agent")
        return 1
    monkeypatch.setattr(scripts_ui.AiScriptDialog, "exec", fake_exec)
    win.script_watcher.armed_since = None
    win.prompt_new_script_ai()
    ((text, cwd),) = started
    assert Path(cwd) == folder
    prompt = Path(text.split("Read ", 1)[1].split(" and follow", 1)[0])
    body = prompt.read_text(encoding="utf-8")
    assert "A gear rack with adjustable tooth count" in body and str(folder / "a_gear_rack_with.py") in body
    assert win.script_watcher.armed_since is not None
    assert "writing a_gear_rack_with.py" in win.status_label.text()


def test_new_script_with_ai_can_copy_the_instructions_for_a_web_chat(win, folder, monkeypatch):
    from omacad.ui import scripts_ui
    monkeypatch.setattr(win, "_agent_name", lambda: None)
    monkeypatch.setattr(QMessageBox, "exec", lambda box: 0)

    def fake_exec(dlg):
        assert not dlg.btn_agent.isEnabled()
        dlg.edt_wish.setPlainText("Ett hyllplan med hål")
        dlg._done("copy")
        return 1
    monkeypatch.setattr(scripts_ui.AiScriptDialog, "exec", fake_exec)
    win.prompt_new_script_ai()
    text = QApplication.clipboard().text()
    assert text.startswith("# Write an Omacad script") and "Ett hyllplan med hål" in text
    assert "ONE ```python code block" in text and "## API reference" in text


def test_ai_dialog_picks_a_free_file_name(win, folder):
    from omacad.ui.scripts_ui import AiScriptDialog
    dlg = AiScriptDialog(win, folder, "Claude Code")
    dlg.edt_wish.setPlainText("gear generator please")
    assert dlg.file_name() == "gear_generator_please.py"
    dlg.edt_name.setText("gear_generator.py")
    assert dlg.file_name() == "gear_generator_2.py"              # the example already has that name
    dlg.deleteLater()


def test_scripts_window_lists_scripts_and_copies_an_error_for_the_ai(win, folder):
    from omacad.ui.scripts_ui import ScriptsDialog
    (folder / "broken.py").write_text("PARAMS = 5\ndef run(ctx, params): pass\n", encoding="utf-8")
    dlg = ScriptsDialog(win, win.script_watcher)
    names = [dlg.list.item(i).text() for i in range(dlg.list.count())]
    assert "⚠ Broken" in names and any(n.endswith("Gear generator") for n in names)
    dlg.list.setCurrentRow(names.index("⚠ Broken"))
    assert not dlg.btn_run.isEnabled() and dlg.btn_copy.isEnabled()
    dlg._copy_error()
    assert "PARAMS must be a list" in QApplication.clipboard().text()
    dlg.reject()


def test_settings_dialog_saves_the_scripts_folder(win, tmp_path):
    from omacad.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(win)
    dlg.edt_scripts_folder.setText(str(tmp_path / "elsewhere"))
    dlg.accept()
    assert get_settings().get("scripts_folder") == str(tmp_path / "elsewhere")
    assert win.scripts_folder() == tmp_path / "elsewhere"


def test_tool_submenus_list_the_scripts_and_modify(win, folder):
    from PySide6.QtWidgets import QMenu
    from omacad.ui import script_menus
    for cid, script in (("jar", "Jar with Lid (script)"), ("star_brackets", "Star Brackets (script)"),
                        ("box_row", "Box in a Row (script)")):
        menu = QMenu()
        got = {"tool": 0, "run": [], "modify": []}
        script_menus.fill_family_menu(menu, cid, lambda: got.__setitem__("tool", got["tool"] + 1), win.family_scripts,
                                      got["run"].append, got["modify"].append)
        texts = [a.text() for a in menu.actions() if not a.isSeparator()]
        assert texts[0].endswith("(built-in)") and script in texts and texts[-1] == "Modify with AI…"
        next(a for a in menu.actions() if a.text() == script).trigger()
        menu.actions()[0].trigger()
        menu.actions()[-1].trigger()
        assert got["tool"] == 1 and got["modify"] == [script_menus.FAMILIES[cid]]
        assert Path(got["run"][0]).name in ("jar_with_lid.py", "star_brackets.py", "box_in_a_row.py")


def test_ribbon_dropdown_and_create_menu_have_the_submenus(win, folder):
    titles = lambda m: [a.text() for a in m.actions()]
    if "primitives" in win.ribbon.command_buttons:
        prim = win.ribbon.command_buttons["primitives"].menu()
        subs = {a.text(): a.menu() for a in prim.actions() if a.menu() is not None}
    else:
        subs = {"Jar with Lid": win.ribbon.command_buttons["jar"].menu()}
    jar = subs["Jar with Lid"]
    jar.aboutToShow.emit()
    assert "Jar with Lid (script)" in titles(jar)
    create = next(a.menu() for a in win.menuBar().actions() if a.text() == "Create")
    prim_menu = next(a.menu() for a in create.actions() if a.menu() is not None and a.text() == "Primitives")
    names = [a.text() for a in prim_menu.actions() if a.menu() is not None]
    assert {"Jar with Lid", "Star Brackets", "Box in a Row"} <= set(names)
    # a new copy shows up the next time the menu opens
    (folder / "jar_big.py").write_text("NAME = 'Big jar'\nFAMILY = 'jar'\ndef run(ctx, params): ctx.box(1, 1, 1)\n",
                                       encoding="utf-8")
    jar.aboutToShow.emit()
    assert "Big jar" in titles(jar)


def test_modify_with_ai_copies_and_leaves_the_original(win, folder, monkeypatch):
    from omacad import feedback
    from omacad.ui import scripts_ui
    started = []
    monkeypatch.setattr(win, "_agent_name", lambda: "Claude Code")
    monkeypatch.setattr(feedback, "launch_agent_text", lambda text, cwd, choice=None: started.append(text) or True)
    original = (folder / "star_brackets.py").read_text(encoding="utf-8")

    def fake_exec(dlg):
        assert dlg.windowTitle() == "Modify with AI" and dlg.base().name == "star_brackets.py"
        dlg.edt_wish.setPlainText("Rounder brackets")
        dlg._done("agent")
        return 1
    monkeypatch.setattr(scripts_ui.AiScriptDialog, "exec", fake_exec)
    win.prompt_modify_script("star_brackets")
    copy = folder / "star_brackets_rounder_brackets.py"
    assert copy.exists() and (folder / "star_brackets.py").read_text(encoding="utf-8") == original
    assert read_info(copy).family == "star_brackets" and read_info(copy).name == "Star Brackets – Rounder brackets"
    prompt = Path(started[0].split("Read ", 1)[1].split(" and follow", 1)[0]).read_text(encoding="utf-8")
    assert "# Change an Omacad script" in prompt and str(copy) in prompt and "NEVER change it" in prompt
    assert "Star Brackets – Rounder brackets" in [i.name for i in win.family_scripts("star_brackets")]


def test_params_panel_has_a_name_field_that_is_remembered(win, folder, monkeypatch):
    from omacad.ui import scripts_ui
    gear = folder / "gear_generator.py"
    get_settings().set("trusted_scripts", sfolder.trust({}, gear))
    seen = []

    def fake_exec(dlg):
        seen.append(dlg.edt_name.text())
        dlg.edt_name.setText("Drev 12")
        dlg.fields["teeth"][1].setValue(12)
        return 1
    monkeypatch.setattr(scripts_ui.ScriptParamsDialog, "exec", fake_exec)
    assert win.run_user_script(gear)
    assert seen == ["Gear"] and "Drev 12" in [o.name for o in win.doc.object_history.objects.values()]
    assert win.run_user_script(gear)
    assert seen == ["Gear", "Drev 12"]                          # the last name is offered again
