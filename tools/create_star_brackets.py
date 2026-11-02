#!/usr/bin/env python3
"""
tools/create_star_brackets.py

Creates parametric 3D-printable brackets and foot supports for a Christmas star (julstjärna)
built from square aluminum tubes (default 10 mm).

Features created:
1. Outer bracket (Spetsfäste, 36° default for 5-pointed star)
2. Inner bracket (Dalfäste, 108° default for 5-pointed star)
3. Foot support (Stötta / Fot med stabil markplatta för bottenrören)

All dimensions are fully editable in the Browser tree under '⚙️ Settings' in Omacad Hybrid!

Usage:
    python tools/create_star_brackets.py [options]

Options:
    --tube-size FLOAT        Tube dimension in mm (default: 10.0)
    --clearance FLOAT        3D print clearance in mm (default: 0.25)
    --wall-thickness FLOAT   Plastic wall thickness in mm (default: 2.5)
    --socket-depth FLOAT     Insertion depth for tube in mm (default: 25.0)
    --hole-dia FLOAT         Screw hole diameter in mm (default: 3.5)
    --hole-offset FLOAT      Distance from arm opening to hole in mm (default: 12.0)
    --outer-angle FLOAT      Outer tip angle in degrees (default: 36.0 for 5-pointed star)
    --inner-angle FLOAT      Inner valley angle in degrees (default: 108.0 for 5-pointed star)
    --foot-width FLOAT       Ground plate width in mm (default: 40.0)
    --foot-length FLOAT      Ground plate length in mm (default: 70.0)
    --foot-thickness FLOAT   Ground plate thickness in mm (default: 4.0)
    --foot-angle FLOAT       Bottom tube slant to ground in degrees (default: 36.0)
    --output FILE            Output .omacad project path (default: julstjarna_fasten.omacad)
    --export-stl             Also export STL files for direct 3D printing
"""

import sys
import os
import argparse
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

# Offscreen Qt platform for headless document generation
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from omacad.model.document import Document
from omacad.io.exporter import Exporter


def main():
    parser = argparse.ArgumentParser(description="Create Omacad Hybrid parametric project for star brackets.")
    parser.add_argument("--tube-size", type=float, default=10.0, help="Square tube nominal dimension (mm)")
    parser.add_argument("--tube-length", type=float, default=250.0, help="Square tube length (mm)")
    parser.add_argument("--clearance", type=float, default=0.25, help="3D printing tolerance fit (mm)")
    parser.add_argument("--wall-thickness", type=float, default=2.5, help="Wall thickness around socket (mm)")
    parser.add_argument("--socket-depth", type=float, default=25.0, help="Depth of tube socket (mm)")
    parser.add_argument("--hole-dia", type=float, default=3.5, help="Screw hole diameter (mm)")
    parser.add_argument("--hole-offset", type=float, default=12.0, help="Screw hole distance from arm end (mm)")
    parser.add_argument("--outer-angle", type=float, default=36.0, help="Outer apex angle in degrees (36° for 5-pointed star)")
    parser.add_argument("--inner-angle", type=float, default=108.0, help="Inner valley angle in degrees (108° for 5-pointed star)")
    parser.add_argument("--foot-width", type=float, default=40.0, help="Base plate width (mm)")
    parser.add_argument("--foot-length", type=float, default=70.0, help="Base plate length (mm)")
    parser.add_argument("--foot-thickness", type=float, default=4.0, help="Base plate thickness (mm)")
    parser.add_argument("--foot-angle", type=float, default=36.0, help="Foot tube slant to ground (degrees)")
    parser.add_argument("--assembled", action="store_true", help="Generate full assembled star view (10 tubes + 10 brackets + 2 feet)")
    parser.add_argument("--output", type=str, default="julstjarna_fasten.omacad", help="Output .omacad project file")
    parser.add_argument("--export-stl", action="store_true", help="Also export individual STL files for 3D printing")

    args = parser.parse_args()

    doc = Document("Julstjärna fästen")
    bodies = doc.add_star_brackets(
        tube_size=args.tube_size,
        tube_length=args.tube_length,
        clearance=args.clearance,
        wall_thickness=args.wall_thickness,
        socket_depth=args.socket_depth,
        hole_diameter=args.hole_dia,
        hole_offset=args.hole_offset,
        outer_angle=args.outer_angle,
        inner_angle=args.inner_angle,
        foot_width=args.foot_width,
        foot_length=args.foot_length,
        foot_thickness=args.foot_thickness,
        foot_tube_angle=args.foot_angle,
        assembled=args.assembled,
        group_name="Julstjärna fästen",
    )

    out_path = Path(args.output).resolve()
    Exporter.save_project(doc, str(out_path))
    print(f"✓ Sparade Omacad-projekt: {out_path}")
    print(f"  Modeller skapade: {len(bodies)}")
    for b in bodies:
        bounds = b.manifold.bounding_box()
        size_x = bounds[3] - bounds[0]
        size_y = bounds[4] - bounds[1]
        size_z = bounds[5] - bounds[2]
        print(f"  • {b.name}: {size_x:.1f} × {size_y:.1f} × {size_z:.1f} mm")

    if args.export_stl:
        out_dir = out_path.parent
        for b in bodies:
            slug = b.name.lower().replace(" ", "_")
            stl_file = out_dir / f"{slug}.stl"
            Exporter.export_body_to_stl(b, str(stl_file))
            print(f"✓ Exporterade STL: {stl_file}")

    print("\nÖppna filen i Omacad Hybrid:")
    print(f"  omacad-hybrid {out_path}")
    print("Alla mått kan nu justeras direkt i trädet under '⚙️ Settings' med pennan eller dubbelklick!")


if __name__ == "__main__":
    main()
