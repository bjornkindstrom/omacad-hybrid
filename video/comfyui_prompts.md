# ComfyUI prompts for the Omacad intro

Suggested: SDXL or Flux, 1920x1080 (16:9) for cards, 1280x720 for the thumbnail. Keep the colours close to the app theme (dark background, one accent colour). Add real UI screenshots on top; use the generated images as backdrops, not as a picture of the app.

**Common negative prompt:** `text, letters, watermark, logo, signature, blurry, low quality, extra fingers, deformed, cluttered`

## 1. Title card background
`dark minimal workshop desk at night, soft blue and teal rim light, glowing wireframe of a machined aluminium bracket floating above a blueprint grid, shallow depth of field, cinematic, ultra clean, 8k, volumetric light`

## 2. Parametric idea (b-roll)
`a perforated metal plate with a perfect hexagon honeycomb pattern and four corner screw holes, macro photography, brushed aluminium, studio lighting, dark background, teal accent glow, sharp focus`

## 3. Blueprint to part (transition)
`technical blueprint with white lines on deep blue paper dissolving into a real CNC-machined part, split composition, exploded view lines, engineering drawing aesthetic, high detail`

## 4. Linux desk (intro mood)
`tidy dark desk setup, tiling window manager on an ultrawide monitor showing abstract 3D wireframe, mechanical keyboard, warm lamp, moody, photorealistic, shallow depth of field`

## 5. Undo / never lose work (metaphor)
`a glowing timeline of translucent cubes stepping backwards in time, each cube a stage of a machined part, dark background, teal light trails, minimal, 3D render`

## 6. End card background
`calm dark gradient background, subtle blueprint grid fading out, a single small glowing geometric part in the lower right, large empty area on the left for text, minimal, 8k`

## 7. Thumbnail
`close-up of a rounded rectangular aluminium plate with a hexagon honeycomb cut-out and four corner holes, dramatic teal and orange rim light, dark background, large empty space on the right for big text, ultra sharp, product photography`
Overlay text in the editor: **NATIVE CAD** (bold, 2 words max).

## Tips
- Generate 4 variants per prompt, pick the cleanest geometry.
- Do not ask ComfyUI for text; add it in the editor.
- Img2img from a real Omacad screenshot (denoise 0.35-0.5) gives backdrops that match the real UI.
