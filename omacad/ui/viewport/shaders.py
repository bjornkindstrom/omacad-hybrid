"""OpenGL Shaders for Omacad 3D Viewport."""

# Shaders
VERTEX_SHADER_SOLID = """
#version 120
attribute vec3 in_pos;
attribute vec3 in_normal;
uniform mat4 u_mvp;
varying vec3 v_normal;
void main() {
    v_normal = in_normal;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER_SOLID = """
#version 120
varying vec3 v_normal;
uniform vec4 u_color;
void main() {
    vec3 n = normalize(v_normal);
    // Two-point CAD lighting setup
    vec3 light1 = normalize(vec3(0.5, 0.7, 1.0));
    vec3 light2 = normalize(vec3(-0.5, -0.6, 0.4));
    float diff1 = max(dot(n, light1), 0.0);
    float diff2 = max(dot(n, light2), 0.0) * 0.35;
    float ambient = 0.38;
    float lighting = clamp(diff1 + diff2 + ambient, 0.0, 1.0);
    gl_FragColor = vec4(u_color.rgb * lighting, u_color.a);
}
"""

VERTEX_SHADER_FLAT = """
#version 120
attribute vec3 in_pos;
uniform mat4 u_mvp;
void main() {
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER_FLAT = """
#version 120
uniform vec4 u_color;
void main() {
    gl_FragColor = u_color;
}
"""

VERTEX_SHADER_TEXTURE = """
#version 120
attribute vec3 in_pos;
attribute vec2 in_uv;
uniform mat4 u_mvp;
varying vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER_TEXTURE = """
#version 120
varying vec2 v_uv;
uniform sampler2D u_tex;
uniform float u_opacity;
void main() {
    vec4 col = texture2D(u_tex, v_uv);
    gl_FragColor = vec4(col.rgb, col.a * u_opacity);
}
"""

# Screen-space thick lines (glLineWidth > 1 is invalid in this context)
VERTEX_SHADER_THICK = """
#version 120
attribute vec3 in_pos;
attribute vec3 in_other;
attribute float in_side;
uniform mat4 u_mvp;
uniform vec2 u_viewport;
uniform float u_width;
void main() {
    vec4 c0 = u_mvp * vec4(in_pos, 1.0);
    vec4 c1 = u_mvp * vec4(in_other, 1.0);
    vec2 s0 = c0.xy / c0.w * u_viewport * 0.5;
    vec2 s1 = c1.xy / c1.w * u_viewport * 0.5;
    vec2 d = s0 - s1;
    float len = length(d);
    d = len > 1e-6 ? d / len : vec2(1.0, 0.0);
    vec2 n = vec2(-d.y, d.x);
    vec2 off = (n * in_side + d) * (u_width * 0.5);
    gl_Position = c0 + vec4(off / (u_viewport * 0.5) * c0.w, 0.0, 0.0);
}
"""

SKETCH_GROUP_ICONS = {"Create": "✏️", "Modify": "🛠️"}
