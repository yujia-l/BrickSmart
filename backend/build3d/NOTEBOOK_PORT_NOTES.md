# Notebook Port Notes

This folder contains the production version of the exploratory notebook:

`Block_Instructions (pre-connection)/my_notebook_25 (CSP).ipynb`

The goal is to keep the working notebook logic available to the orchestration
pipeline without making the app execute an `.ipynb` file directly.

## Notebook Stage Map

| Original notebook stage | Production module | Purpose |
| --- | --- | --- |
| Load segmented OBJ | `voxelizer.py` | Reads Rodin/Bang OBJ groups and tracks segment ids. |
| Voxelize source segments | `voxelizer.py` | Samples OBJ triangles into a 32x32x32 segmented voxel grid. |
| Clean voxel grid | `voxelizer.py` | Snaps occupied areas to 2x2 footprints, removes tiny vertical noise, and splits disconnected segment components. |
| Render segment views | `notebook_outputs.py` | Writes segment visualization and front/back/left/right/top/bottom/iso multiview images. |
| Detect segment adjacency/interfaces | `voxelizer.py` | Builds segment adjacency and contact-surface records from actual neighboring voxels. |
| Map teacher movement intent | `notebook_outputs.py` | Matches teacher-named moving parts to segment labels and contact surfaces. |
| Generate connector candidates | `notebook_outputs.py` | Converts movement types into connector-site candidates such as axle, wheel axle, hinge, and slider. |
| Convert voxels to blocks | `block_decomposer.py` | Turns 2x2 columns into 2x2x2, 2x2x3, and 2x2x4 block instances. |
| Assign block faces | `block_decomposer.py` | Uses male/female/none face templates from the notebook. |
| Optimize block rotations | `csp_solver.py` | Runs CSP-style rotation scoring and connectivity energy. |
| Validate physical build | `connectivity.py` | Reports connected components, face conflicts, bridge blocks, and attachment degrees. |
| Render final and step images | `notebook_outputs.py` | Writes final block reference, single-step images, and per-step multiview placement sheets. |
| Generate teacher/student steps | `instructions.py` | Turns step blocks, segment labels, inventory, and connector notes into guide text. |

## Important Output Contract

`generate_notebook_outputs(...)` writes `notebook_outputs/manifest.json` and
returns the same object to the build plan. The UI and final teacher manual read
these fields:

- `voxel_size`: the grid resolution used for teacher-facing physicalization.
  The default is `16`, which intentionally makes chunkier and more readable
  classroom instructions than the earlier `32` diagnostic grid.
- `clean_segments`: whether the notebook cleanup pass was applied before block
  decomposition. Keep this configurable because cleanup reduces noise but can
  remove thin details on some generated models.
- `final_image`: final BrickSmart block reference.
- `segment_multiview_image`: notebook-style source segment views.
- `instruction_steps[].image_path`: single isometric image for a build step.
- `instruction_steps[].multiview_path`: broken-down placement sheet for that step.
- `block_inventory`: generated block counts by size/color.
- `connector_candidates`: teacher movement intent mapped onto actual segment contacts.
- `validation`: physical buildability summary.
- `connectivity_report`: detailed low-level block interface report.

## Movement And Connectors

Movement is intentionally used twice:

1. Before Rodin: the prompt asks the model to visually separate teacher-named
   moving parts so Bang can segment them.
2. After Bang: the voxel/contact stage checks whether those moving parts have
   real contact surfaces that can support a connector.

This keeps the code general. A propeller, wheel, flap, door, lever, or any
future teacher-named moving part follows the same path: teacher intent ->
segment match -> contact surface -> connector candidate -> teacher approval.

## Current Limits

- Segment matching is label/token based. The planned LLM vision labeling pass
  should replace or supplement this when stable segment thumbnails are available.
- Connector candidates identify likely sites; exact part-specific geometry still
  needs the real BrickSmart inventory model.
- The validation layer separates hard conflicts from review-required flat or
  connector contacts, but it is not yet a full structural simulator.
