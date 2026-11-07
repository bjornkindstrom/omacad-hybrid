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
uniform vec3 u_eye_dir;
void main() {
    vec3 n = normalize(v_normal);
    vec3 v = length(u_eye_dir) > 0.01 ? normalize(u_eye_dir) : normalize(vec3(0.5, 0.7, 1.0));
    // SolidCraft studio lighting: double-sided normal flip so interior/back faces stay lit
    if (dot(n, v) < 0.0) {
        n = -n;
    }
    // Key light offset slightly above and to the side relative to camera view
    vec3 key = normalize(v * 0.8 + vec3(-0.35, 0.25, 0.65));
    float diff = max(dot(n, key), 0.0);
    float fill = max(dot(n, v), 0.0);
    vec3 h = normalize(key + v);
    float spec = pow(max(dot(n, h), 0.0), 32.0) * 0.22;
    // Ambient / sky gradient: upward-facing surfaces get subtle sky reflection
    float sky = dot(n, vec3(0.0, 0.0, 1.0)) * 0.12 + 0.36;
    float k = clamp(sky + 0.40 * diff + 0.22 * fill, 0.0, 1.0);
    gl_FragColor = vec4(min(u_color.rgb * k + vec3(spec), vec3(1.0)), u_color.a);
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
