from omacad.scripting.loader import read_info
from omacad.ui.script_easy import save_easy
from omacad.ui.scripts_ui import ScriptParamsDialog


def test_easy_roundtrip_and_visibility(tmp_path):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "demo.py"
    path.write_text('NAME = "Demo"\nPARAMS = [{"name": "size", "default": 10}, {"name": "detail", "default": 3}]\ndef run(ctx, params): pass\n')
    save_easy(path, ["size"])
    save_easy(path, [])
    assert read_info(path).easy_params == []
    save_easy(path, ["size"])
    info = read_info(path)
    dlg = ScriptParamsDialog(info, {"size": 20, "detail": 7})
    dlg.mode.setCurrentText("Easy")
    assert dlg.fields["detail"][1].isHidden()
    assert not dlg.fields["size"][1].isHidden()
    assert dlg.values()["detail"] == 7
    dlg.mode.setCurrentText("Advanced")
    assert not dlg.fields["detail"][1].isHidden()
    dlg.close()


def test_easy_labels_order_and_empty_selection(tmp_path):
    from PySide6.QtWidgets import QApplication, QFormLayout
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "ordered.py"
    path.write_text('PARAMS = [{"name": "a", "default": 1}, {"name": "b", "default": 2}, {"name": "c", "default": 3}]\ndef run(ctx, params): pass\n')
    save_easy(path, ["c", "a"])
    dlg = ScriptParamsDialog(read_info(path), {})
    dlg.show()
    dlg.mode.setCurrentText("Easy")
    app.processEvents()
    form = dlg.param_form
    b = dlg.fields["b"][1]
    assert not b.isVisible()
    assert not form.labelForField(b).isVisible()
    assert form.getWidgetPosition(dlg.fields["c"][1])[0] == 1
    assert form.getWidgetPosition(dlg.fields["a"][1])[0] == 2
    dlg.mode.setCurrentText("Advanced")
    assert b.isVisible() and form.labelForField(b).isVisible()
    assert form.getWidgetPosition(dlg.fields["a"][1])[0] == 1
    dlg.info.easy_params = []
    dlg.mode.setCurrentText("Easy")
    assert all(not w.isVisible() and not form.labelForField(w).isVisible()
               for _, w in dlg.fields.values())
    assert dlg.values() == {"a": 1, "b": 2, "c": 3}
    dlg.close()


def test_easy_start_only_constructs_selected_fields(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "start.py"
    path.write_text('PARAMS = [{"name": "a", "default": 1}, {"name": "b", "default": 2}]\ndef run(ctx, params): pass\n')
    save_easy(path, ["b"])
    created = []
    field = ScriptParamsDialog._field
    def track(param, value):
        created.append(param.name)
        return field(param, value)
    monkeypatch.setattr(ScriptParamsDialog, "_field", staticmethod(track))
    dlg = ScriptParamsDialog(read_info(path), {"a": 9}, mode="Easy")
    assert dlg.mode.currentText() == "Easy"
    assert created == ["b"]
    assert dlg.values() == {"a": 9, "b": 2}
    dlg.fields["b"][1].setValue(4)
    dlg.mode.setCurrentText("Advanced")
    assert created == ["b", "a"]
    assert dlg.values() == {"a": 9, "b": 4}
    dlg.mode.setCurrentText("Easy")
    assert dlg.fields["a"][1].isHidden()
    dlg.close()
