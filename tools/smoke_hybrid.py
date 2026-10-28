#!/usr/bin/env python3
"""Exercise the real Qt/OpenGL viewport; capture it and optionally leave it open."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QTimer
from PySide6.QtGui import QSurfaceFormat
from PySide6.QtWidgets import QApplication, QLabel
import numpy as np

from omacad import viewport_accel
from omacad.ui.main_window import MainWindow
from omacad.ui.controllers.file_session import FileSessionMixin
from omacad.ui import theme
from omacad.model import faces_hit_tests


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--output",type=Path,required=True);parser.add_argument("--keep-open",action="store_true");args=parser.parse_args()
    fmt=QSurfaceFormat();fmt.setSamples(4);fmt.setDepthBufferSize(24);fmt.setStencilBufferSize(8);fmt.setVersion(3,3);fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CompatibilityProfile);QSurfaceFormat.setDefaultFormat(fmt)
    app=QApplication([]);app.setApplicationName("Omacad Hybrid");app.setOrganizationName("Omacad Hybrid")
    app.setStyle(theme.BigIconStyle("Fusion"));theme.apply_saved_choice()
    window=MainWindow();window.resize(1500,960)
    box=window.doc.add_box(60,40,20,outer_round=3.0)
    window.doc.add_cylinder(10,32,translation=[85,20,0])
    window.doc.add_sphere(12,translation=[-30,20,12])
    window.viewport.target=np.array([30.,20.,8.],dtype=np.float32);window.viewport.distance=230.;window.viewport.azimuth=35.;window.viewport.elevation=28.
    window.statusBar().addPermanentWidget(QLabel(f"Viewport picking: {viewport_accel.backend_name().upper()}"))
    window.show()
    result={"backend":viewport_accel.backend_name(),"ok":False}
    def check():
        try:
            vp=window.viewport
            assert vp.isValid(),"Qt OpenGL context is invalid"
            point=vp.world_to_screen(np.array([30.,20.,20.]))
            assert vp.pick_body(*point)==box.body_id,"Viewport did not pick the test body"
            vp._update_edge_hover(*point)
            if viewport_accel.backend_name()=="rust":
                assert getattr(box.render_mesh,"_native_pick_index",None) is not None
                assert any(v[3] is not None for v in faces_hit_tests._FACE_STACKS.values())
            args.output.parent.mkdir(parents=True,exist_ok=True)
            assert vp.grabFramebuffer().save(str(args.output)),"Could not save OpenGL framebuffer"
            assert window.grab().save(str(args.output.with_name(args.output.stem+"-window.png")))
            result["ok"]=True
            print(json.dumps(result),flush=True)
        except Exception as error:
            result["error"]=repr(error);print(json.dumps(result),flush=True)
        if not args.keep_open or not result["ok"]:
            FileSessionMixin._ask_save_changes=lambda self,name:"discard"
            window.close();app.quit()
    QTimer.singleShot(1600,check)
    app.exec()
    return 0 if result["ok"] else 1

if __name__=="__main__":raise SystemExit(main())
