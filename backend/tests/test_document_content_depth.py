from build3d.pipeline import (
    _lesson_plan_markdown,
    _slide_companion_markdown,
    _validate_document,
)


def _context():
    return {
        "storybook_title": "Milo's Flying Delivery",
        "grade_band": "1st Grade",
        "duration_minutes": 40,
        "theme": "perseverance and teamwork",
        "artifact_label": "Flying Delivery Vehicle",
        "parts": [
            {"part_name": "Propeller", "movement": "spinning"},
            {"part_name": "Body", "movement": "static"},
        ],
        "learning_objectives": ["I can build and test a model."],
        "literacy_focus": "Vocabulary and sound awareness",
        "sel_focus": "Learning from testing",
    }


def _build_plan():
    return {
        "artifact_label": "Flying Delivery Vehicle",
        "notebook_outputs": {
            "final_image": "final.png",
            "segment_multiview_image": "multiview.png",
            "instruction_steps": [
                {
                    "step_number": 1,
                    "student_instruction": "Connect the base pieces.",
                    "teacher_instruction": "Help students compare the base.",
                    "inventory": [{"quantity": 2, "piece": "2x2 block"}],
                    "image_path": "step.png",
                    "multiview_path": "step_multiview.png",
                }
            ],
        },
    }


def test_short_teacher_package_is_expanded_to_reference_depth():
    package = {
        "teacher_plan": {
            "title": "Milo Lesson",
            "overview": "Students read and build.",
            "anticipatory_set": "Ask what students know.",
            "step_01_read": "Read the story.",
            "step_02_learn_explore": "Study the parts.",
            "step_03_invent": "Build the model.",
            "closure_reflection": "Share the model.",
        }
    }
    markdown = _lesson_plan_markdown(package, _build_plan(), _context())
    validation = _validate_document("lesson_plan", markdown, _build_plan())

    assert validation["is_valid"], validation["missing"]
    assert "**Story-to-build connection:**" in markdown
    assert "**Interactive read-aloud:**" in markdown
    assert "**Test and improve:**" in markdown
    assert len(markdown.split()) > 900


def test_slide_companion_has_projectable_prompts_and_notebook_images():
    markdown = _slide_companion_markdown({}, _build_plan(), _context())
    validation = _validate_document("slide_companion", markdown, _build_plan())

    assert validation["is_valid"], validation["missing"]
    assert "## Slide 5 - Sound Detective" in markdown
    assert "## Slide 10 - Build Step 1" in markdown
    assert "## Slide 11 - Check Build Step 1" in markdown
    assert "Image: step.png" in markdown
    assert "Placement views: step_multiview.png" in markdown
