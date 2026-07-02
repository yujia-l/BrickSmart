"""
Temp / mock data for Phase 1 agent development.

Provides hardcoded knowledge-base evidence, policy rules, and block catalog
so agents can be tested end-to-end without a real database or ingestion
pipeline.
"""

from models.schemas import (
    EvidenceCard,
    EvidencePack,
    KidSparkPiece,
    TraceEntry,
)

# ---------------------------------------------------------------------------
# Mock KB evidence — based on the "Invent an Airplane" bundle from the spec
# ---------------------------------------------------------------------------

MOCK_EVIDENCE_CARDS: list[EvidenceCard] = [
    EvidenceCard(
        node_id="teacher.overview",
        bundle_id="storytime_inventing.grade1.invent_an_airplane",
        content_text=(
            "Students will hear a story about perseverance and invention, "
            "then design and build their own airplane using Kid Spark blocks. "
            "The lesson integrates literacy, STEM concepts, and social-emotional learning."
        ),
        doc_kind="teacher_plan",
        audience="teacher",
        lesson_stage="overview",
        relevance_score=0.92,
    ),
    EvidenceCard(
        node_id="teacher.objectives",
        bundle_id="storytime_inventing.grade1.invent_an_airplane",
        content_text=(
            "Learning Objectives: 1) I can build a model of an airplane. "
            "2) I can tell about the parts of my airplane and why I chose them. "
            "3) I can work with a partner to solve building challenges."
        ),
        doc_kind="teacher_plan",
        audience="teacher",
        lesson_stage="overview",
        relevance_score=0.89,
    ),
    EvidenceCard(
        node_id="teacher.step03.invent",
        bundle_id="storytime_inventing.grade1.invent_an_airplane",
        content_text=(
            "Students will build an airplane using the Kid Spark Early Inventors "
            "STEM Lab. This can be done individually or with a partner. If students "
            "need help getting started, display the Example Airplane build plans "
            "from the Slide Companion. Key parts: wings, body, propeller, rudder, "
            "landing gear."
        ),
        doc_kind="teacher_plan",
        audience="teacher",
        lesson_stage="invent",
        relevance_score=0.95,
    ),
    EvidenceCard(
        node_id="teacher.vocabulary",
        bundle_id="storytime_inventing.grade1.invent_an_airplane",
        content_text=(
            "Lesson Vocabulary: airplane, propeller, wings, rudder, fuselage, "
            "design, engineer, invention, perseverance."
        ),
        doc_kind="teacher_plan",
        audience="teacher",
        lesson_stage="overview",
        relevance_score=0.80,
    ),
    EvidenceCard(
        node_id="activity.p1.read",
        bundle_id="storytime_inventing.grade1.invent_an_airplane",
        content_text=(
            "Read the story 'Jabari Tries' aloud. Ask: What did Jabari want to "
            "build? What happened when his first design didn't work? How did he "
            "feel? What did he do next?"
        ),
        doc_kind="activity_guide",
        audience="student",
        lesson_stage="read",
        relevance_score=0.85,
    ),
    EvidenceCard(
        node_id="slide.p10.parts_diagram",
        bundle_id="storytime_inventing.grade1.invent_an_airplane",
        content_text=(
            "Parts diagram slide showing labeled airplane components: wings, "
            "body/fuselage, propeller, rudder, landing gear. Each part is "
            "color-coded to match the Kid Spark block colors used in the build."
        ),
        doc_kind="slide_companion",
        audience="student",
        lesson_stage="learn_explore",
        relevance_score=0.78,
    ),
]

MOCK_POLICY_CARDS: list[EvidenceCard] = [
    EvidenceCard(
        node_id="policy.grade1.NGSS.K-2-ETS1-2",
        bundle_id="policy",
        content_text=(
            "NGSS K-2-ETS1-2: Develop a simple sketch, drawing, or physical model "
            "to illustrate how the shape of an object helps it function as needed "
            "to solve a given problem."
        ),
        doc_kind="policy",
        audience="teacher",
        lesson_stage="standards",
        relevance_score=1.0,
    ),
    EvidenceCard(
        node_id="policy.grade1.CASEL",
        bundle_id="policy",
        content_text=(
            "CASEL Competencies 1-5 for 1st Grade Storytime Inventing: "
            "Self-Awareness, Self-Management, Social Awareness, Relationship "
            "Skills, Responsible Decision-Making. Lessons should include partner "
            "talk, community agreements, and reflection on collaboration."
        ),
        doc_kind="policy",
        audience="teacher",
        lesson_stage="standards",
        relevance_score=1.0,
    ),
    EvidenceCard(
        node_id="policy.grade1.UDL",
        bundle_id="policy",
        content_text=(
            "UDL: Multiple Means of Engagement, Representation, and Action & "
            "Expression. Ensure visual, verbal, and tactile methods are used. "
            "Provide sentence stems for partner talk. Offer example builds for "
            "students who need scaffolding."
        ),
        doc_kind="policy",
        audience="teacher",
        lesson_stage="standards",
        relevance_score=1.0,
    ),
    EvidenceCard(
        node_id="policy.grade1.SoR",
        bundle_id="policy",
        content_text=(
            "Science of Reading: For 1st Grade, include phonemic awareness "
            "through initial sound identification (e.g., 'Aa is for airplane'). "
            "Feature vocabulary with definitions and context sentences. "
            "Include rhyming or word family activities when possible."
        ),
        doc_kind="policy",
        audience="teacher",
        lesson_stage="standards",
        relevance_score=1.0,
    ),
]


def get_mock_evidence(grade_band: str = "1st Grade") -> EvidencePack:
    """Return a mock EvidencePack seeded with airplane bundle data."""
    return EvidencePack(
        teacher_cards=[c for c in MOCK_EVIDENCE_CARDS if c.audience == "teacher"],
        student_cards=[c for c in MOCK_EVIDENCE_CARDS if c.audience == "student"],
        visual_cards=[c for c in MOCK_EVIDENCE_CARDS if c.doc_kind == "slide_companion"],
        policy_cards=MOCK_POLICY_CARDS,
        trace=[
            TraceEntry(
                node_id=c.node_id,
                bundle_id=c.bundle_id,
                score=c.relevance_score,
                retrieval_reason="mock_similarity_search",
            )
            for c in MOCK_EVIDENCE_CARDS[:3]
        ],
    )


def format_evidence_for_prompt(evidence: EvidencePack) -> str:
    """Render evidence into a text block suitable for injection into prompts."""
    lines: list[str] = []

    if evidence.teacher_cards:
        lines.append("=== Existing Lesson Examples (Teacher Plans) ===")
        for card in evidence.teacher_cards:
            lines.append(
                f"[{card.node_id}] ({card.bundle_id})\n{card.content_text}\n"
            )

    if evidence.student_cards:
        lines.append("=== Student Activity Guide Excerpts ===")
        for card in evidence.student_cards:
            lines.append(
                f"[{card.node_id}] ({card.bundle_id})\n{card.content_text}\n"
            )

    if evidence.policy_cards:
        lines.append("=== Curriculum Policy Rules ===")
        for card in evidence.policy_cards:
            lines.append(f"[{card.node_id}] {card.content_text}\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Mock block catalog
# ---------------------------------------------------------------------------

MOCK_BLOCK_CATALOG: list[KidSparkPiece] = [
    KidSparkPiece(
        piece_type="cube",
        piece_name="Cube Block (Windowed)",
        colors_available=["Red", "Blue", "Green", "Yellow", "Purple", "Orange"],
        quantity_per_kit=16,
        connection_mechanism="triangular prism connector",
        supports_rotation=False,
        supports_pivot=False,
        supports_axle=True,
        structural_role="body",
        dimensions={"width": 1, "height": 1, "depth": 1},
        description="Standard building block with windows on each face for connectors.",
    ),
    KidSparkPiece(
        piece_type="half_circle",
        piece_name="Half-Circle Block",
        colors_available=["Pink", "Blue"],
        quantity_per_kit=4,
        connection_mechanism="triangular prism connector",
        supports_rotation=False,
        supports_pivot=False,
        supports_axle=False,
        structural_role="body",
        dimensions={"width": 1, "height": 0.5, "depth": 1},
        description="Curved block for rounded shapes.",
    ),
    KidSparkPiece(
        piece_type="wheel_axle",
        piece_name="Wheel / Axle Assembly",
        colors_available=["Black", "Red"],
        quantity_per_kit=4,
        connection_mechanism="axle-through",
        supports_rotation=True,
        supports_pivot=False,
        supports_axle=True,
        structural_role="articulation",
        dimensions={"width": 1, "height": 1, "depth": 0.5},
        description="Axle passes through a cube block window; attached piece spins freely.",
    ),
    KidSparkPiece(
        piece_type="flat_connector",
        piece_name="Flat Connector",
        colors_available=["Various"],
        quantity_per_kit=10,
        connection_mechanism="bridge",
        supports_rotation=False,
        supports_pivot=False,
        supports_axle=False,
        structural_role="connector",
        dimensions={"width": 1, "height": 0.25, "depth": 1},
        description="Bridges two cube faces that don't share a direct edge.",
    ),
    KidSparkPiece(
        piece_type="angle_connector",
        piece_name="Angle Connector",
        colors_available=["Red"],
        quantity_per_kit=6,
        connection_mechanism="hinge",
        supports_rotation=False,
        supports_pivot=True,
        supports_axle=False,
        structural_role="connector",
        dimensions={"width": 1, "height": 1, "depth": 1},
        description="Corner/angled connection; one cube can hinge relative to another.",
    ),
]


# ---------------------------------------------------------------------------
# Sample storybook text for demo / testing
# ---------------------------------------------------------------------------

SAMPLE_STORYBOOK_TEXT = """\
Milo's Flying Delivery

Milo was a young inventor who loved building things in his workshop. His
grandmother, Grandma Rose, ran a small bakery on the other side of town.
Every Saturday, Milo walked her fresh-baked cookies to their neighbors.

One rainy Saturday, Milo had an idea. "What if I could fly the cookies
to everyone?" He grabbed his toolbox and started designing a flying
delivery vehicle.

His first attempt crashed into the garden fence. His second attempt
flew sideways into a tree. Milo felt frustrated, but Grandma Rose
reminded him: "Every great inventor learns from what didn't work."

Milo asked his neighborhood friends for help. Together, they redesigned
the wings to be wider, added a stronger propeller, and built a secure
cargo compartment for the cookies.

On the next attempt, the flying delivery vehicle soared over the
rooftops! Milo delivered cookies to every neighbor, and everyone
cheered. Milo learned that perseverance and teamwork can turn any
idea into reality.
"""
