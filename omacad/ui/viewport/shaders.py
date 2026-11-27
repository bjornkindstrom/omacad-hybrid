"""OpenGL Shaders for Omacad 3D Viewport.

GLSL 3.30 core: compiles in an OpenGL 3.3 Core *and* Compatibility context on every driver
(Mesa, NVIDIA, AMD, Intel Windows). The old `#version 120` shaders were refused by Mesa in a
Core Profile context, and Intel's Windows driver gave GL_INVALID_OPERATION in Compatibility.
"""

# Shaders
VERTEX_SHADER_SOLID = """
#version 330 core
in vec3 in_pos;
in vec3 in_normal;
uniform mat4 u_mvp;
out vec3 v_normal;
void main() {
    v_normal = in_normal;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER_SOLID = """
#version 330 core
in vec3 v_normal;
uniform vec4 u_color;
uniform vec3 u_eye_dir;
out vec4 frag_color;
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
    float spec = pow(max(dot(n, h), 0.0), 48.0) * 0.20 + pow(max(dot(n, h), 0.0), 8.0) * 0.04;
    // Hemisphere ambient: faces looking up catch the sky, faces looking down the darker ground bounce
    float sky = mix(0.24, 0.44, n.z * 0.5 + 0.5);
    // A faint light from below and behind, so undersides keep their shape instead of going flat grey
    float under = max(dot(n, normalize(vec3(0.3, -0.45, -0.85))), 0.0) * 0.07;
    // Rim: a soft brightening at grazing angles separates the silhouette from the backdrop
    float rim = pow(1.0 - fill, 3.0) * 0.14;
    float k = clamp(sky + 0.40 * diff + 0.26 * fill + under, 0.0, 1.0);
    vec3 col = u_color.rgb * k + vec3(spec) + rim * mix(u_color.rgb, vec3(1.0), 0.6);
    frag_color = vec4(min(col, vec3(1.0)), u_color.a);
}
"""

VERTEX_SHADER_FLAT = """
#version 330 core
in vec3 in_pos;
uniform mat4 u_mvp;
void main() {
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER_FLAT = """
#version 330 core
uniform vec4 u_color;
out vec4 frag_color;
void main() {
    frag_color = u_color;
}
"""

VERTEX_SHADER_TEXTURE = """
#version 330 core
in vec3 in_pos;
in vec2 in_uv;
uniform mat4 u_mvp;
out vec2 v_uv;
void main() {
    v_uv = in_uv;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER_TEXTURE = """
#version 330 core
in vec2 v_uv;
uniform sampler2D u_tex;
uniform float u_opacity;
out vec4 frag_color;
void main() {
    vec4 col = texture(u_tex, v_uv);
    frag_color = vec4(col.rgb, col.a * u_opacity);
}
"""

# Screen-space thick lines (glLineWidth > 1 is invalid in this context)
VERTEX_SHADER_THICK = """
#version 330 core
in vec3 in_pos;
in vec3 in_other;
in float in_side;
uniform mat4 u_mvp;
uniform vec2 u_viewport;
uniform float u_width;
uniform float u_depth_bias;   // pulls body edges a hair towards the eye so the faces they border never cover them
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
    gl_Position = c0 + vec4(off / (u_viewport * 0.5) * c0.w, -u_depth_bias * c0.w, 0.0);
}
"""

SKETCH_GROUP_ICONS = {"Create": "✏️", "Modify": "🛠️"}

# Backdrop: a full-screen quad with a soft vertical gradient (lighter at the top), dithered against banding
VERTEX_SHADER_BACKDROP = """
#version 330 core
in vec2 in_xy;
out float v_t;
void main() {
    v_t = in_xy.y * 0.5 + 0.5;
    gl_Position = vec4(in_xy, 0.0, 1.0);
}
"""

FRAGMENT_SHADER_BACKDROP = """
#version 330 core
in float v_t;
uniform vec3 u_top;
uniform vec3 u_bottom;
out vec4 frag_color;
void main() {
    float t = smoothstep(0.0, 1.0, v_t);
    float noise = fract(sin(dot(gl_FragCoord.xy, vec2(12.9898, 78.233))) * 43758.5453) - 0.5;
    frag_color = vec4(mix(u_bottom, u_top, t) + noise / 255.0, 1.0);
}
"""

# Grid lines that fade out towards the edge of the grid instead of stopping at a hard line or crowding the horizon
VERTEX_SHADER_GRID = """
#version 330 core
in vec3 in_pos;
uniform mat4 u_mvp;
out vec3 v_world;
void main() {
    v_world = in_pos;
    gl_Position = u_mvp * vec4(in_pos, 1.0);
}
"""

FRAGMENT_SHADER_GRID = """
#version 330 core
in vec3 v_world;
uniform vec4 u_color;
uniform vec3 u_center;
uniform float u_fade_start;
uniform float u_fade_end;
out vec4 frag_color;
void main() {
    float d = distance(v_world, u_center);
    float fade = 1.0 - smoothstep(u_fade_start, u_fade_end, d);
    frag_color = vec4(u_color.rgb, u_color.a * fade);
}
"""
