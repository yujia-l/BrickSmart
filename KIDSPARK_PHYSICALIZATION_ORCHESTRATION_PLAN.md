# KidSpark Physicalization Orchestration Plan

## Goal

Turn teacher-approved story and movement intent into a BrickSmart lesson package with physical block instructions that are reviewable before the final classroom document is approved.

## Updated Flow

1. Intake story source
   - Teacher uploads a PDF or pastes story text.
   - The ingestion layer extracts story text, themes, vocabulary, SEL opportunities, buildable objects, and standards anchors.

2. Guided teacher conversation
   - The agent confirms grade, time, lesson target, literacy objective, SEL objective, and build artifact.
   - The agent asks which parts should move and how: static, spinning, rolling, pivoting, sliding, or teacher-described custom movement.
   - The output is a teacher-approved movement plan, not a model-generation guess.

3. Pre-build confirmation
   - Teacher reviews artifact, standards, and moving/static parts before Rodin credits are spent.
   - The approved movement plan becomes structured `parts` plus a readable `teacher_connection_intent`.

4. Rodin/Bang generation
   - Rodin receives both the object prompt and the movement plan.
   - The prompt asks for visibly separated moving parts so Bang can segment them.
   - Bang returns the segmented OBJ used by the physicalization stage.

5. Voxel and segment physicalization
   - `voxelizer.py` loads the segmented OBJ, voxelizes it, cleans 2x2 footprints, splits connected components, and detects segment contact surfaces.
   - Segment labels come from the teacher/context table and can be edited in the UI.

6. Movement-aware connector site proposal
   - Teacher movement intent is matched to Bang segments by label/source-name tokens.
   - Actual voxel contact surfaces are searched for matching moving-part segments.
   - Candidate connector sites are produced generically for movement types:
     - spinning -> `axle_rotation`
     - rolling -> `wheel_axle`
     - pivoting -> `hinge_connector`
     - sliding -> `slider_connector`
     - static -> `static_snap`
   - If no contact surface is found, the UI marks the connector as needing teacher placement review.

7. Block decomposition and CSP validation
   - `block_decomposer.py` converts voxel columns into 2x2x2, 2x2x3, and 2x2x4 block instances.
   - `csp_solver.py` optimizes block rotations using face compatibility and connectivity energy.
   - `connectivity.py` reports components, hard face conflicts, bridge blocks, and per-interface attachment status.

8. Teacher verification checkpoints
   - Teacher reviews the Rodin/Bang asset.
   - Teacher edits/approves segment labels.
   - Teacher edits/approves connection labels and connector sites.
   - Teacher reviews final block image, inventory, physical validation metrics, and step images.
   - Teacher can request a rebuild before approving the final document.

9. Final output
   - The teacher manual includes lesson plan, standards anchor, inventory, movement connector sites, physical validation summary, final built reference image, and step-by-step teacher/student instructions.

## Why Movement Goes to Both Rodin and Voxel/CSP

Rodin needs movement context early so the generated source model separates important moving parts. The voxel/CSP stage needs the same teacher intent later so it can test whether those moving parts have usable physical contact surfaces and connector locations. Using both stages keeps the system general: it does not assume a plane, wheel, or propeller; it treats movement as structured intent attached to teacher-named parts.

## Current Implementation Components

- `backend/build3d/voxelizer.py`: segmented OBJ loading, voxelization, cleanup, adjacency, contact surfaces.
- `backend/build3d/block_decomposer.py`: notebook-style block instances, inventory, staggered 2x2 column decomposition.
- `backend/build3d/csp_solver.py`: block face rotation optimization and connectivity energy.
- `backend/build3d/connectivity.py`: physical validation report.
- `backend/build3d/instructions.py`: segment-to-step teacher/student instructions.
- `backend/build3d/notebook_outputs.py`: orchestration wrapper that writes the notebook/CSP manifest and images.
- `pages/kidspark.py` and `pages/kidspark_demo.py`: teacher review UI for physical validation and connector candidates.

## Remaining Hardening

- Add the LLM vision labeling loop for segment labels once stable segment render thumbnails are available.
- Add teacher-edit persistence back into regenerated CSV files, so UI edits can rerun physicalization.
- Expand connector libraries beyond the current generic movement-to-connector mapping as real BrickSmart part metadata becomes available.
- Add a rebuild endpoint that passes teacher connector edits back into Rodin prompt and voxel validation.
