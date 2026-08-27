# Structural planner and global inventory coordination

The validated row/column structural planner is implemented as standalone backend
Python code.

The planner consumes one normalized model contract, the shared XLSX block
catalog, and a separate run-level inventory profile. It does not inspect a named
model profile or branch on object category.

## Scope

The structural planner is responsible for source-segment structural modules and
their generic joins.

Reusable capability handlers are responsible for wheels, hinges, rotation
mechanisms, replacements, in-between connectors, and other declared functional
assemblies.

The assembly layer sequences structural modules and functional assemblies into
the final build.

## Inputs

The planner receives:

- a resolved immutable OBJ;
- contract-defined coordinate transforms and preprocessing;
- confirmed source-segment meanings;
- structural packing configuration;
- symmetry and interface declarations;
- the XLSX block catalog;
- a run-level inventory profile;
- declared reusable functional capabilities.

## Preserved mechanics

- contract-controlled OBJ voxelization and preprocessing;
- authoritative segment confirmation and lineage;
- structuralization onto the catalog-compatible lattice;
- disconnected-component handling;
- segment-local row and column packing;
- candidate build-axis evaluation;
- catalog-driven dimensions, rotations, colors, male faces, and female faces;
- mirrored structural planning;
- direct male-to-female locking validation;
- segment-module construction followed by module assembly;
- structuralization, coverage, contact, and repair gates.

## Planning flow

```text
Resolve and validate model contract
        ↓
Voxelize and preserve source-segment lineage
        ↓
Apply confirmed segment semantics
        ↓
Structuralize onto the supported lattice
        ↓
Generate mechanically valid alternatives per segment
        ↓
Evaluate axes, packing, rotations, and locking contacts
        ↓
Coordinate symmetry and whole-model inventory
        ↓
Commit complete segment and functional requirements atomically
        ↓
Construct segment modules
        ↓
Join modules and functional assemblies
        ↓
Sequence true build steps
        ↓
Independently validate final parts and inventory
```

## Catalog-driven candidate generation

Every candidate block must resolve through
`block_catalog/block_definitions.xlsx`.

The workbook is authoritative for:

- block dimensions;
- visible and reserved occupancy;
- allowed rotations;
- male and female connector faces;
- packing priorities;
- colors;
- functional metadata.

The planner must not synthesize unsupported block dimensions or maintain a
shadow CSV definition.

## Segment-local row and column packing

Packing operates within the source-segment region while preserving lineage.

The contract may configure candidate axes, row/column progression, temporary
module roots, symmetry, and final connectivity requirements. These values tune
generic algorithms and must not name a model-specific Python routine.

Candidate selection should prefer mechanically valid arrangements that satisfy
coverage, contact, orientation, inventory, and contract requirements.

## Structural joins

The currently validated structural join mode is:

```text
direct_structural_lock
```

A direct structural lock requires a valid catalog-defined male-to-female contact
in the selected orientations.

A new join mode requires a reusable join-capability handler with generic
contract fields and tests. It must not be implemented as a branch for a
particular model category.

## Symmetry

Symmetry declarations may coordinate:

- mirrored source segments;
- mirrored candidate selection;
- block-family counts;
- orientations;
- functional target pairing;
- atomic inventory reservation.

Symmetry must not override geometry, connector compatibility, collision, or
inventory constraints.

## Global inventory coordination

### Principles

The row/column engine owns geometry, rotations, locking contacts, and build
order. The inventory layer chooses only among mechanically valid alternatives.

Inventory commitments remain deferred until the whole required group can be
evaluated.

### Allocation flow

```text
Generate mechanically valid segment alternatives
        ↓
Keep inventory commitments deferred
        ↓
Reserve contract-required functional components
        ↓
Deduplicate components represented at more than one declaration layer
        ↓
Evaluate the whole model against one inventory profile
        ↓
Commit atomically only when every required group is represented
        ↓
Build segment modules and assemble them
        ↓
Independently recount final parts
```

### Functional reservations

Required functional components are reserved before structural alternatives are
committed when the contract makes those components mandatory.

A physical component may be represented by both:

- a `functional_attachments` target declaration; and
- a connector field within a larger `functional_assemblies` declaration.

The runtime deduplicates reserves by physical target and block family so the
same physical component is reserved once.

### Atomic groups

Mirrored pairs, mandatory functional groups, or other contract-defined complete
sets should commit atomically. A partial allocation must not consume inventory
when another required member of the same group cannot be satisfied.

Failed alternatives must release provisional reservations.

### Unlimited inventory

Unlimited inventory is an explicit execution mode used for geometry or
reference-scale validation. It must be recorded in run metadata and must not be
mistaken for standard-kit feasibility.

### Independent recount

After final parts are selected, validation independently recounts every block
family and compares it with:

- initial inventory capacity;
- committed reservation ledger;
- final parts;
- replacement and functional allocations.

The final build claim fails when the recount disagrees with either capacity or
the committed ledger.

## Planner outputs

Important outputs include:

```text
global_inventory_allocation.json
inventory_validation.json
final_parts.csv
parts_by_step.csv
build_instructions.json
build_instructions.html
final_build_claim_summary.json
```

`global_inventory_allocation.json` records candidate requirements, fixed
functional reserves, aggregate demand, shortages, segment completeness,
reservation identity, and commit status.

`inventory_validation.json` independently compares the final-parts recount with
inventory capacity and the committed ledger.

`build_instructions.html` is the canonical human-readable instruction artifact.
For validated row/column builds it contains the self-contained interactive 3D
player and step panel. `build_instructions.json` remains the structured form for
APIs, tests, and downstream systems.

Exact artifact availability may vary by build path, but equivalent evidence
must remain available for final validation.

## Repair and fallback behavior

Repair may operate only within validated generic rules. It must preserve source
lineage, use catalog-defined blocks and rotations, respect committed inventory,
and pass the same collision and contact gates as primary planning.

The older greedy cuboid OBJ planner may remain available only as an explicitly
experimental comparison command. It is not the validated row/column placement
engine and must not silently replace it after a failure.

## Final structural gates

Before the structural plan can support a final `PASS` claim, validate:

- source coverage and lineage;
- catalog conformance;
- collisions and reserved occupancy;
- allowed rotations;
- required locking contacts;
- segment-module connectivity;
- required module joins;
- symmetry;
- inventory allocation and recount;
- build-step completeness and prerequisites.
