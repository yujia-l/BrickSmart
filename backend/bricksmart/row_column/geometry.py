"""Pure geometry and lattice helpers for row/column planning."""

from __future__ import annotations

import io
import re
from collections import Counter, defaultdict
from enum import Enum
from itertools import permutations, product

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from PIL import Image


class FaceType(Enum):
    MALE = 1
    FEMALE = 2
    NONE = 0


def normalize_meshes(segmented_meshes):
    # Compute global bounds
    """Normalize meshes.
    
    :param segmented_meshes: The segmented meshes value.
    :returns: The computed result.
    """
    all_vertices = np.vstack([m.vertices for _, m in segmented_meshes])

    min_bound = all_vertices.min(axis=0)
    max_bound = all_vertices.max(axis=0)

    scale = (max_bound - min_bound).max()

    normalized = []
    for sid, mesh in segmented_meshes:
        m = mesh.copy()
        m.apply_translation(-min_bound)
        m.apply_scale(1.0 / scale)
        normalized.append((sid, m))

    return normalized


def enforce_2x2_footprint(voxel_matrix):
    """Return the enforce 2x2 footprint value.
    
    :param voxel_matrix: The voxel matrix value.
    :returns: The result produced by the function.
    """
    sx, sy, sz = voxel_matrix.shape
    snapped = np.zeros_like(voxel_matrix)

    for x in range(0, sx-1, 2):
        for y in range(0, sy-1, 2):
            block = voxel_matrix[x:x+2, y:y+2, :]

            # If ANY voxel exists in this 2x2 column → fill footprint
            mask = np.any(block > 0, axis=(0,1))
            for z in np.where(mask)[0]:
                color = np.bincount(block[:,:,z].flatten()[block[:,:,z].flatten()>0]).argmax()
                snapped[x:x+2, y:y+2, z] = color

    return snapped


def clean_vertical_columns(voxel_matrix):
    """Return the clean vertical columns value.
    
    :param voxel_matrix: The voxel matrix value.
    :returns: The result produced by the function.
    """
    cleaned = voxel_matrix.copy()
    sx, sy, sz = voxel_matrix.shape

    for x in range(sx):
        for y in range(sy):
            column = voxel_matrix[x, y, :]
            filled = np.where(column > 0)[0]

            if len(filled) == 0:
                continue

            z_min = filled.min()
            z_max = filled.max()
            height = z_max - z_min + 1

            if height < 2:
                cleaned[x, y, :] = 0
                continue

            remaining = height
            valid_height = 0

            for block in [4, 3, 2]:
                count = remaining // block
                valid_height += count * block
                remaining -= count * block

            if valid_height < height:
                cleaned[x, y, z_min + valid_height : z_max + 1] = 0

    return cleaned


def thicken_floor_and_ceiling_per_column(voxel_matrix):
    """
    For each 2x2 column:
    - If the floor is 1 voxel thick, add 1 voxel below (toward interior)
    - If the ceiling is 1 voxel thick, add 1 voxel above (toward interior)
    Assumes the surface shell is already voxelized.
    """
    sx, sy, sz = voxel_matrix.shape
    new_voxel = voxel_matrix.copy()

    # Loop over all 2x2 footprints
    for x in range(0, sx - 1):
        for y in range(0, sy - 1):

            # Extract the vertical column
            column = new_voxel[x:x+2, y:y+2, :]
            filled = np.where(np.any(column > 0, axis=(0,1)))[0]

            if len(filled) == 0:
                continue

            # Floor: z_min
            z_min = filled.min()
            if z_min + 1 <= sz - 1:
                # Check if floor is only 1 voxel thick
                if np.all(column[:, :, z_min+1] == 0):
                    column[:, :, z_min+1] = column[:, :, z_min]

            # Ceiling: z_max
            z_max = filled.max()
            if z_max - 1 >= 0:
                # Check if ceiling is only 1 voxel thick
                if np.all(column[:, :, z_max-1] == 0):
                    column[:, :, z_max-1] = column[:, :, z_max]

            # Write back
            new_voxel[x:x+2, y:y+2, :] = column

    return new_voxel


def remap_segments_to_2x2_grid(voxel_segment, voxel_structure):
    """
    Reassign segment IDs based on 2x2 structural footprint.
    """

    x_size, y_size, z_size = voxel_segment.shape
    new_seg = np.zeros_like(voxel_segment)

    for x in range(0, x_size, 2):
        for y in range(0, y_size, 2):

            # collect all segments in this 2x2 column
            segment_votes = []

            for dx in range(2):
                for dy in range(2):

                    xx = x + dx
                    yy = y + dy

                    if xx >= x_size or yy >= y_size:
                        continue

                    for z in range(z_size):
                        if voxel_structure[xx, yy, z] > 0:
                            segment_votes.append(voxel_segment[xx, yy, z])

            if len(segment_votes) == 0:
                continue

            # majority vote (dominant segment wins)
            dominant_segment = Counter(segment_votes).most_common(1)[0][0]

            # assign to full 2x2 column
            for dx in range(2):
                for dy in range(2):
                    xx = x + dx
                    yy = y + dy

                    if xx >= x_size or yy >= y_size:
                        continue

                    for z in range(z_size):
                        if voxel_structure[xx, yy, z] > 0:
                            new_seg[xx, yy, z] = dominant_segment

    return new_seg


def compute_segment_adjacency(voxel_segment):
    """Compute segment adjacency.
    
    :param voxel_segment: The voxel segment value.
    :returns: The computed result.
    """
    sx, sy, sz = voxel_segment.shape
    adjacency = set()

    directions = [(1,0,0), (0,1,0), (0,0,1)]

    for x in range(sx):
        for y in range(sy):
            for z in range(sz):
                s1 = voxel_segment[x,y,z]
                if s1 == 0: continue

                for dx,dy,dz in directions:
                    nx, ny, nz = x+dx, y+dy, z+dz
                    if nx>=sx or ny>=sy or nz>=sz: continue

                    s2 = voxel_segment[nx,ny,nz]
                    if s2 != 0 and s2 != s1:
                        adjacency.add(tuple(sorted((s1, s2))))

    return list(adjacency)


def compute_contact_surfaces(voxel_segment):
    """Compute contact surfaces.
    
    :param voxel_segment: The voxel segment value.
    :returns: The computed result.
    """
    sx, sy, sz = voxel_segment.shape

    directions = [
        (1,0,0), (-1,0,0),
        (0,1,0), (0,-1,0),
        (0,0,1), (0,0,-1)
    ]

    contacts = defaultdict(list)

    for x in range(sx):
        for y in range(sy):
            for z in range(sz):

                s1 = voxel_segment[x, y, z]
                if s1 == 0:
                    continue

                for dx, dy, dz in directions:
                    nx, ny, nz = x + dx, y + dy, z + dz

                    if (
                        0 <= nx < sx and
                        0 <= ny < sy and
                        0 <= nz < sz
                    ):
                        s2 = voxel_segment[nx, ny, nz]

                        if s2 != 0 and s2 != s1:
                            key = (min(s1, s2), max(s1, s2))

                            contacts[key].append({
                                "pos": (x, y, z),
                                "normal": (dx, dy, dz)
                            })

    return contacts


def normalize_voxel_axes(voxel_segment):
    # OBJ/trimesh fix: swap Y and Z into visualization convention
    """Normalize voxel axes.
    
    :param voxel_segment: The voxel segment value.
    :returns: The computed result.
    """
    return np.transpose(voxel_segment, (0, 2, 1))


def render_voxel_view(voxel_segment, elev, azim, segment_colors):

    """Render voxel view.
    
    :param voxel_segment: The voxel segment value.
    :param elev: The elev value.
    :param azim: The azim value.
    :param segment_colors: The segment colors value.
    :returns: The result produced by the function.
    """
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')

    filled = voxel_segment > 0
    colors = np.zeros(voxel_segment.shape + (3,), dtype=np.float32)

    for sid, color in segment_colors.items():
        mask = voxel_segment == sid
        colors[mask] = np.array(color) / 255.0

    ax.voxels(filled, facecolors=colors, edgecolor='none', alpha=1.0)

    ax.set_xlim(0, voxel_segment.shape[0])
    ax.set_ylim(0, voxel_segment.shape[1])
    ax.set_zlim(0, voxel_segment.shape[2])

    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight', dpi=150)
    plt.close(fig)

    buf.seek(0)
    return Image.open(buf)


def parse_catalog_faces(value):
    """Parse catalog faces.
    
    :param value: Value used by the operation.
    :returns: The computed result.
    """
    return tuple(
        dict.fromkeys(
            re.findall(r"[+-][XYZ]", str(value or ""))
        )
    )


def normalized_rotation(rotation):
    """Return normalized rotation.
    
    :param rotation: The rotation value.
    :returns: The result produced by the function.
    """
    return (int(rotation) // 90 % 4) * 90


def block_bounds(block):
    """Return block bounds.
    
    :param block: Block record used by the operation.
    :returns: The result produced by the function.
    """
    x0, y0, z0 = (int(v) for v in block.position)
    dx, dy, dz = (int(v) for v in block.size)
    return x0, x0 + dx, y0, y0 + dy, z0, z0 + dz


def positive_overlap(a0, a1, b0, b1):
    """Return the positive overlap value.
    
    :param a0: The a0 value.
    :param a1: The a1 value.
    :param b0: The b0 value.
    :param b1: The b1 value.
    :returns: The result produced by the function.
    """
    return max(0, min(a1, b1) - max(a0, b0))


def face_area(block, face):
    """Return face area.
    
    :param block: Block record used by the operation.
    :param face: The face value.
    :returns: The result produced by the function.
    """
    dx, dy, dz = (int(v) for v in block.size)

    if face in {"+X", "-X"}:
        return dy * dz
    if face in {"+Y", "-Y"}:
        return dx * dz
    if face in {"+Z", "-Z"}:
        return dx * dy

    raise KeyError(face)


def touching_face_geometry(block_a, block_b):
    """
    Return exact shared faces and overlap area for axis-aligned blocks.

    This is geometry-only. Face polarity is evaluated separately for each
    candidate rotation assignment.
    """
    ax0, ax1, ay0, ay1, az0, az1 = block_bounds(block_a)
    bx0, bx1, by0, by1, bz0, bz1 = block_bounds(block_b)

    ox = positive_overlap(ax0, ax1, bx0, bx1)
    oy = positive_overlap(ay0, ay1, by0, by1)
    oz = positive_overlap(az0, az1, bz0, bz1)


    # Positive-volume overlap is an invalid placement.

    if ox > 0 and oy > 0 and oz > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": None,
            "face_b": None,
            "overlap_area": None,
            "geometry_status": "geometric_overlap_conflict",
        }

    if ax1 == bx0 and oy > 0 and oz > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "+X",
            "face_b": "-X",
            "overlap_area": int(oy * oz),
            "geometry_status": "face_contact",
        }

    if bx1 == ax0 and oy > 0 and oz > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "-X",
            "face_b": "+X",
            "overlap_area": int(oy * oz),
            "geometry_status": "face_contact",
        }

    if ay1 == by0 and ox > 0 and oz > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "+Y",
            "face_b": "-Y",
            "overlap_area": int(ox * oz),
            "geometry_status": "face_contact",
        }

    if by1 == ay0 and ox > 0 and oz > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "-Y",
            "face_b": "+Y",
            "overlap_area": int(ox * oz),
            "geometry_status": "face_contact",
        }

    if az1 == bz0 and ox > 0 and oy > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "+Z",
            "face_b": "-Z",
            "overlap_area": int(ox * oy),
            "geometry_status": "face_contact",
        }

    if bz1 == az0 and ox > 0 and oy > 0:
        return {
            "block_a": int(block_a.block_id),
            "block_b": int(block_b.block_id),
            "face_a": "-Z",
            "face_b": "+Z",
            "overlap_area": int(ox * oy),
            "geometry_status": "face_contact",
        }

    return None


def geometry_contacts(blocks_a, blocks_b=None):
    """Return the geometry contacts value.
    
    :param blocks_a: The blocks a value.
    :param blocks_b: The blocks b value.
    :returns: The result produced by the function.
    """
    rows = []

    if blocks_b is None:
        for i in range(len(blocks_a)):
            for j in range(i + 1, len(blocks_a)):
                row = touching_face_geometry(blocks_a[i], blocks_a[j])
                if row is not None:
                    rows.append(row)
        return rows

    for block_a in blocks_a:
        for block_b in blocks_b:
            if int(block_a.block_id) == int(block_b.block_id):
                continue

            row = touching_face_geometry(block_a, block_b)
            if row is not None:
                rows.append(row)

    return rows


def classify_face_types(type_a, type_b):
    """Return the classify face types value.
    
    :param type_a: The type a value.
    :param type_b: The type b value.
    :returns: The result produced by the function.
    """
    if {type_a, type_b} == {"male", "female"}:
        return "male_to_female_lock"
    if type_a == "male" and type_b == "male":
        return "male_to_male_conflict"
    if type_a == "female" and type_b == "female":
        return "female_to_female_nonlocking"
    return "unresolved_or_none"


def actual_block_face_type(block, face):
    """Return actual block face type.
    
    :param block: Block record used by the operation.
    :param face: The face value.
    :returns: The result produced by the function.
    """
    template = None if block.faces is None else block.faces.get(face)

    if template is None:
        return "none"

    values = list(np.asarray(template, dtype=object).ravel())
    has_male = any(v == FaceType.MALE for v in values)
    has_female = any(v == FaceType.FEMALE for v in values)

    if has_male and has_female:
        return "mixed"
    if has_male:
        return "male"
    if has_female:
        return "female"
    return "none"


def rotation_matrices_24():
    """Return rotation matrices 24.
    
    :returns: The result produced by the function.
    """
    matrices = []
    basis = np.eye(3, dtype=int)
    for permutation in permutations(range(3)):
        permutation_matrix = basis[:, permutation]
        for signs in product([-1, 1], repeat=3):
            matrix = permutation_matrix @ np.diag(signs)
            determinant = round(np.linalg.det(matrix))
            if determinant == 1:
                matrices.append(matrix)
    unique = {}
    for matrix in matrices:
        unique[tuple(matrix.ravel().tolist())] = matrix
    return list(unique.values())


def mirror_index_coordinate(index, center_plane):
    """Mirror index coordinate.
    
    :param index: The index value.
    :param center_plane: The center plane value.
    :returns: The result produced by the function.
    """
    mirrored = 2.0 * float(center_plane) - (float(index) + 0.5)
    return int(round(mirrored - 0.5))


def mirror_mask(mask, axis, center_plane):
    """Mirror mask.
    
    :param mask: The mask value.
    :param axis: The axis value.
    :param center_plane: The center plane value.
    :returns: The result produced by the function.
    """
    mask = np.asarray(mask, dtype=bool)
    mirrored = np.zeros_like(mask, dtype=bool)
    for coordinate in np.argwhere(mask):
        reflected = coordinate.astype(int).copy()
        reflected[axis] = mirror_index_coordinate(
            reflected[axis],
            center_plane,
        )
        if all(
            0 <= reflected[current_axis] < mask.shape[current_axis]
            for current_axis in range(3)
        ):
            mirrored[tuple(reflected)] = True
    return mirrored


def mask_iou(mask_a, mask_b):
    """Build mask from iou.
    
    :param mask_a: The mask a value.
    :param mask_b: The mask b value.
    :returns: The result produced by the function.
    """
    mask_a = np.asarray(mask_a, dtype=bool)
    mask_b = np.asarray(mask_b, dtype=bool)
    union = int((mask_a | mask_b).sum())
    if union == 0:
        return 1.0
    return float((mask_a & mask_b).sum() / union)


def box_coordinates(origin, size):
    """Return the box coordinates value.
    
    :param origin: The origin value.
    :param size: The size value.
    :returns: The result produced by the function.
    """
    x0, y0, z0 = (int(value) for value in origin)
    dx, dy, dz = (int(value) for value in size)
    return [
        (x, y, z)
        for x in range(x0, x0 + dx)
        for y in range(y0, y0 + dy)
        for z in range(z0, z0 + dz)
    ]


def box_mask(shape, origin, size):
    """Return the box mask value.
    
    :param shape: The shape value.
    :param origin: The origin value.
    :param size: The size value.
    :returns: The result produced by the function.
    """
    mask = np.zeros(shape, dtype=bool)
    x0, y0, z0 = (int(value) for value in origin)
    dx, dy, dz = (int(value) for value in size)
    if (
        x0 < 0 or y0 < 0 or z0 < 0
        or x0 + dx > shape[0]
        or y0 + dy > shape[1]
        or z0 + dz > shape[2]
    ):
        return None
    mask[
        x0:x0 + dx,
        y0:y0 + dy,
        z0:z0 + dz,
    ] = True
    return mask


def clipped_box_mask(
    shape,
    origin,
    size,
):
    """Return the clipped box mask value.
    
    :param shape: The shape value.
    :param origin: The origin value.
    :param size: The size value.
    :returns: The result produced by the function.
    """
    starts = [
        max(
            0,
            int(
                origin[
                    axis
                ]
            ),
        )
        for axis in range(
            3
        )
    ]
    ends = [
        min(
            int(
                shape[
                    axis
                ]
            ),
            int(
                origin[
                    axis
                ]
            )
            + int(
                size[
                    axis
                ]
            ),
        )
        for axis in range(
            3
        )
    ]
    if any(
        starts[
            axis
        ]
        >= ends[
            axis
        ]
        for axis in range(
            3
        )
    ):
        return None

    mask = np.zeros(
        shape,
        dtype=bool,
    )
    mask[
        starts[
            0
        ]:
        ends[
            0
        ],
        starts[
            1
        ]:
        ends[
            1
        ],
        starts[
            2
        ]:
        ends[
            2
        ],
    ] = True
    return mask


def mask_coordinate_list(
    mask,
):
    """Build mask from coordinate list.
    
    :param mask: The mask value.
    :returns: The result produced by the function.
    """
    return [
        tuple(
            int(
                value
            )
            for value in coordinate
        )
        for coordinate in np.argwhere(
            mask
        )
    ]


def coordinate_plan_to_world(
    coordinate,
    world_shape,
    quarter_turns,
):
    """Return the coordinate plan to world value.
    
    :param coordinate: The coordinate value.
    :param world_shape: The world shape value.
    :param quarter_turns: The quarter turns value.
    :returns: The result produced by the function.
    """
    px, py, z = (
        int(
            coordinate[
                index
            ]
        )
        for index in range(
            3
        )
    )
    nx = int(
        world_shape[
            0
        ]
    )
    ny = int(
        world_shape[
            1
        ]
    )
    k = int(
        quarter_turns
    ) % 4

    if k == 0:
        return (
            px,
            py,
            z,
        )
    if k == 1:
        return (
            py,
            ny - 1 - px,
            z,
        )
    if k == 2:
        return (
            nx - 1 - px,
            ny - 1 - py,
            z,
        )
    return (
        nx - 1 - py,
        px,
        z,
    )


def cylinder_geometry(origin, size, axis, depth=None, segments=36):
    """Return the cylinder geometry value.
    
    :param origin: The origin value.
    :param size: The size value.
    :param axis: The axis value.
    :param depth: The depth value.
    :param segments: Segment collection used by the operation.
    :returns: The result produced by the function.
    """
    origin = np.asarray(origin, dtype=float)
    size = np.asarray(size, dtype=float)
    center = origin + size / 2.0
    axis = int(axis)
    other = [candidate for candidate in range(3) if candidate != axis]
    radius = 0.48 * min(size[other[0]], size[other[1]])
    depth = float(size[axis] if depth is None else min(depth, size[axis]))
    vertices = []
    for side in [-0.5, 0.5]:
        for theta in np.linspace(0, 2*np.pi, segments, endpoint=False):
            point = center.copy()
            point[axis] += side * depth
            point[other[0]] += radius * np.cos(theta)
            point[other[1]] += radius * np.sin(theta)
            vertices.append(point)
    lower_center = len(vertices)
    point = center.copy()
    point[axis] -= depth / 2
    vertices.append(point)
    upper_center = len(vertices)
    point = center.copy()
    point[axis] += depth / 2
    vertices.append(point)
    triangles = []
    for index in range(segments):
        following = (index + 1) % segments
        lower_a, lower_b = index, following
        upper_a, upper_b = segments + index, segments + following
        triangles.extend([
            [lower_a, lower_b, upper_b],
            [lower_a, upper_b, upper_a],
            [lower_center, lower_b, lower_a],
            [upper_center, upper_a, upper_b],
        ])
    return np.asarray(vertices), np.asarray(triangles, dtype=int)


def point_inside_interval(
    value,
    minimum,
    maximum,
    tolerance=1e-9,
):
    """Return the point inside interval value.
    
    :param value: Value used by the operation.
    :param minimum: The minimum value.
    :param maximum: The maximum value.
    :param tolerance: The tolerance value.
    :returns: The result produced by the function.
    """
    return bool(
        float(minimum) - tolerance
        <= float(value)
        <= float(maximum) + tolerance
    )


def geometry_mask(shape, dataframe, group_column=None, limit_per_group=None):
    """Return the geometry mask value.
    
    :param shape: The shape value.
    :param dataframe: The dataframe value.
    :param group_column: The group column value.
    :param limit_per_group: The limit per group value.
    :returns: The result produced by the function.
    """
    mask = np.zeros(shape,dtype=bool)
    if dataframe is None or dataframe.empty:
        return mask
    selected = dataframe
    if group_column and group_column in selected.columns and limit_per_group:
        groups = []
        for _, group in selected.groupby(group_column,sort=True):
            if "score" in group.columns:
                group = group.sort_values("score",ascending=False)
            groups.append(group.head(int(limit_per_group)))
        if groups:
            selected = pd.concat(groups,ignore_index=True)
    for coordinates in selected.get(
        "geometry_coordinates",pd.Series(dtype=object)
    ):
        for coordinate in coordinates or []:
            coordinate = tuple(int(v) for v in coordinate)
            if all(0 <= coordinate[a] < shape[a] for a in range(3)):
                mask[coordinate] = True
    return mask


def coordinate_in_bounds(coordinate, shape):
    """Return the coordinate in bounds value.
    
    :param coordinate: The coordinate value.
    :param shape: The shape value.
    :returns: The result produced by the function.
    """
    return all(
        0 <= int(coordinate[axis]) < int(shape[axis])
        for axis in range(3)
    )


def coordinate_is_on_block_face(
    block,
    coordinate,
    face,
):
    """Return the coordinate is on block face value.
    
    :param block: Block record used by the operation.
    :param coordinate: The coordinate value.
    :param face: The face value.
    :returns: The result produced by the function.
    """
    coordinate = tuple(
        int(value)
        for value in coordinate
    )
    origin = tuple(
        int(value)
        for value in block.position
    )
    size = tuple(
        int(value)
        for value in block.size
    )
    checks = {
        "+X": (
            coordinate[0]
            == origin[0] + size[0] - 1
        ),
        "-X": coordinate[0] == origin[0],
        "+Y": (
            coordinate[1]
            == origin[1] + size[1] - 1
        ),
        "-Y": coordinate[1] == origin[1],
        "+Z": (
            coordinate[2]
            == origin[2] + size[2] - 1
        ),
        "-Z": coordinate[2] == origin[2],
    }
    return bool(checks[face])


def height_is_catalog_representable(
    height,
    allowed_heights,
):
    """Return the height is catalog representable value.
    
    :param height: The height value.
    :param allowed_heights: The allowed heights value.
    :returns: The result produced by the function.
    """
    height = int(height)
    reachable = [False] * (
        height + 1
    )
    reachable[0] = True
    for value in range(1, height + 1):
        reachable[value] = any(
            value - block_height >= 0
            and reachable[
                value - block_height
            ]
            for block_height in allowed_heights
        )
    return bool(reachable[height])


def connected_component_sizes(
    mask,
):
    """Return the connected component sizes value.
    
    :param mask: The mask value.
    :returns: The result produced by the function.
    """
    remaining = set(
        map(
            tuple,
            np.argwhere(mask),
        )
    )
    sizes = []
    offsets = [
        (1, 0, 0),
        (-1, 0, 0),
        (0, 1, 0),
        (0, -1, 0),
        (0, 0, 1),
        (0, 0, -1),
    ]

    while remaining:
        start = remaining.pop()
        queue = [start]
        size = 1

        while queue:
            coordinate = queue.pop()
            for offset in offsets:
                neighbor = tuple(
                    coordinate[axis]
                    + offset[axis]
                    for axis in range(3)
                )
                if neighbor in remaining:
                    remaining.remove(
                        neighbor
                    )
                    queue.append(
                        neighbor
                    )
                    size += 1

        sizes.append(size)

    return sorted(
        sizes,
        reverse=True,
    )


def exact_lattice_mask(
    mask,
):
    """Return exact lattice mask.
    
    :param mask: The mask value.
    :returns: The result produced by the function.
    """
    shape = mask.shape
    for x in range(
        0,
        shape[0] - 1,
        2,
    ):
        for y in range(
            0,
            shape[1] - 1,
            2,
        ):
            counts = mask[
                x:x + 2,
                y:y + 2,
                :,
            ].sum(
                axis=(0, 1)
            )
            if np.any(
                (counts > 0)
                & (counts < 4)
            ):
                return False
    return True


def align_grid_to_lattice_offset(raw_grid, offset_x, offset_y):
    """Return the align grid to lattice offset value.
    
    :param raw_grid: The raw grid value.
    :param offset_x: The offset x value.
    :param offset_y: The offset y value.
    :returns: The result produced by the function.
    """
    raw_grid = np.asarray(raw_grid, dtype=int)
    offset_x = int(offset_x)
    offset_y = int(offset_y)

    high_x = (2 - ((raw_grid.shape[0] + offset_x) % 2)) % 2
    high_y = (2 - ((raw_grid.shape[1] + offset_y) % 2)) % 2

    aligned = np.pad(
        raw_grid,
        (
            (offset_x, high_x),
            (offset_y, high_y),
            (0, 0),
        ),
        mode="constant",
        constant_values=0,
    )
    transform = {
        "offset_x": offset_x,
        "offset_y": offset_y,
        "low_padding": [offset_x, offset_y, 0],
        "high_padding": [high_x, high_y, 0],
        "source_shape": list(raw_grid.shape),
        "aligned_shape": list(aligned.shape),
    }
    return aligned, transform


def get_face_center(block, face):
    """Return face center.
    
    :param block: Block record used by the operation.
    :param face: The face value.
    :returns: The result produced by the function.
    """
    x, y, z = (
        float(value)
        for value in block.position
    )
    dx, dy, dz = (
        float(value)
        for value in block.size
    )
    centers = {
        "+X": (
            x + dx,
            y + dy / 2.0,
            z + dz / 2.0,
        ),
        "-X": (
            x,
            y + dy / 2.0,
            z + dz / 2.0,
        ),
        "+Y": (
            x + dx / 2.0,
            y + dy,
            z + dz / 2.0,
        ),
        "-Y": (
            x + dx / 2.0,
            y,
            z + dz / 2.0,
        ),
        "+Z": (
            x + dx / 2.0,
            y + dy / 2.0,
            z + dz,
        ),
        "-Z": (
            x + dx / 2.0,
            y + dy / 2.0,
            z,
        ),
    }
    if face not in centers:
        raise ValueError(
            f"Unsupported block face: {face}"
        )
    return centers[face]


def get_face_normal(face):
    """Return face normal.
    
    :param face: The face value.
    :returns: The result produced by the function.
    """
    normals = {
        "+X": (1.0, 0.0, 0.0),
        "-X": (-1.0, 0.0, 0.0),
        "+Y": (0.0, 1.0, 0.0),
        "-Y": (0.0, -1.0, 0.0),
        "+Z": (0.0, 0.0, 1.0),
        "-Z": (0.0, 0.0, -1.0),
    }
    if face not in normals:
        raise ValueError(
            f"Unsupported block face: {face}"
        )
    return normals[face]


def block_contains_voxel(block, coordinate):
    """Return block contains voxel.
    
    :param block: Block record used by the operation.
    :param coordinate: The coordinate value.
    :returns: The result produced by the function.
    """
    return all(
        int(block.position[axis])
        <= int(coordinate[axis])
        < int(block.position[axis])
        + int(block.size[axis])
        for axis in range(3)
    )


__all__ = [
    'block_contains_voxel',
    'FaceType',
    'normalize_meshes',
    'enforce_2x2_footprint',
    'clean_vertical_columns',
    'thicken_floor_and_ceiling_per_column',
    'remap_segments_to_2x2_grid',
    'compute_segment_adjacency',
    'compute_contact_surfaces',
    'normalize_voxel_axes',
    'render_voxel_view',
    'parse_catalog_faces',
    'normalized_rotation',
    'positive_overlap',
    'block_bounds',
    'touching_face_geometry',
    'geometry_contacts',
    'classify_face_types',
    'actual_block_face_type',
    'face_area',
    'box_coordinates',
    'box_mask',
    'clipped_box_mask',
    'mask_coordinate_list',
    'coordinate_plan_to_world',
    'coordinate_in_bounds',
    'coordinate_is_on_block_face',
    'mirror_index_coordinate',
    'mirror_mask',
    'rotation_matrices_24',
    'point_inside_interval',
    'get_face_center',
    'get_face_normal',
    'cylinder_geometry',
    'geometry_mask',
    'height_is_catalog_representable',
    'connected_component_sizes',
    'exact_lattice_mask',
    'align_grid_to_lattice_offset',
    'mask_iou',
]
