"""ctx.adjust / ctx.changed: a script moves another value so the values fit, and the panel shows it."""
from omacad.model.document import Document
from omacad.scripting.loader import read_info
from omacad.scripting.runner import check_report, preview_run, run_script
from omacad.ui.scripts_ui import ScriptParamsDialog

SCRIPT = '''
NAME = "Fit"
PARAMS = [{"name": "outer", "type": "float", "default": 20.0, "min": 1, "max": 100},
          {"name": "inner", "type": "float", "default": 10.0, "min": 1, "max": 100}]

def run(ctx, params):
    if params["inner"] > params["outer"] - 2:
        if ctx.changed == "inner":
            params["outer"] = ctx.adjust("outer", params["inner"] + 2, "outer grown for inner")
        else:
            params["inner"] = ctx.adjust("inner", params["outer"] - 2, "inner shrunk for outer")
    ctx.solid(__import__("manifold3d").Manifold.cylinder(1, params["outer"]), "ring")
'''


def _script(tmp_path):
    path = tmp_path / "fit.py"
    path.write_text(SCRIPT)
    return path


def test_adjusted_values_are_reported_and_stored(tmp_path):
    path = _script(tmp_path)
    res = run_script(Document(), path, {"outer": 20.0, "inner": 30.0}, changed="inner")
    assert res.adjusted == {"outer": 32.0}
    assert res.notes == ["outer grown for inner"]
    assert res.values["outer"] == 32.0 and res.values["inner"] == 30.0
    res = run_script(Document(), path, {"outer": 20.0, "inner": 30.0})
    assert res.adjusted == {"inner": 18.0}
    assert run_script(Document(), path, {}).adjusted == {}
    solid, res = preview_run(path, {"outer": 5.0, "inner": 10.0}, changed="outer")
    assert solid is not None and res.adjusted == {"inner": 3.0}
    ok, report = check_report(path, {"outer": 5.0, "inner": 10.0})
    assert ok and "Adjusted by the script: inner shrunk for outer" in report


def test_panel_takes_adjusted_values_without_a_new_preview(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    dlg = ScriptParamsDialog(read_info(_script(tmp_path)), {})
    fired = []
    dlg.changed.connect(lambda: fired.append(True))
    dlg.fields["inner"][1].setValue(30.0)
    assert dlg.last_changed == "inner" and fired == [True]
    dlg.set_values({"outer": 32.0, "nonsense": 1})
    assert dlg.fields["outer"][1].value() == 32.0 and dlg.values()["outer"] == 32.0
    assert fired == [True]
    dlg.show_notes(["outer grown for inner"])
    assert "outer grown for inner" in dlg.lbl_note.text() and not dlg.lbl_note.isHidden()
    dlg.show_notes([])
    assert dlg.lbl_note.isHidden()
    dlg.close()
    app.processEvents()
