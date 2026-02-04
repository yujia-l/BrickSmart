from typing import List
from pydantic import BaseModel
from structured_query import query_vlm, process_chat_history

prompts = {
    "spatial_selection": '''
    You are a spatial language teacher. Your responsibility is to determine the spatial language tasks to be learned based on the task and the student's situation. Please refer to the following information:
    1. Based on the provided LEGO assembly tutorial image, analyze and describe the current building task in detail, outputting the string parameter instruction:
        (1) The overall structure and design features of the LEGO model shown in the image.
        (2) Identify and describe the types and colors of LEGO parts appearing in the image.
        (3) Point out the assembly steps in the image, including any special assembly techniques or details that need special attention.
        (4) Use professional LEGO terminology to enhance the accuracy and professionalism of the description.
        (5) Ensure that the output text accurately reflects the content of the image, with clear, professional, and detailed language that is easy for the reader to understand the assembly process.
    2. The 8 dimensions of spatial language include:
        (1) Spatial dimensions (size, height, length, width, thickness, depth);
        (2) Shapes (circular, square, rectangular, triangular, spherical, cylindrical, conical);
        (3) Position and direction (front and back, left and right, up and down, inside and outside, middle/side);
        (4) Direction and transformation (left/right, forward/backward, upward/downward);
        (5) Continuous quantity (whole, part, fraction, majority/minority);
        (6) Demonstratives (here, there, where);
        (7) Spatial features and attributes (straight line, curve, circle, angle, point, plane, surface);
        (8) Patterns (next, increase, decrease).
    3. The user's current level of understanding of spatial language is: {understand_level}, which represents the learning progress of the 8 dimensions (expressed as a percentage).
    Determine the 3 most suitable spatial language categories for learning, trying to select categories that are suitable for the current LEGO building task and that the user has not mastered well.
    Output a list spatial_list of length 3, with each element ranging from 0 to 7, representing the index of the spatial language category.
    '''
}


class spatialSelectionOutput(BaseModel):
    instruction: str
    spatial_list: List[int]


def spatial_selection(image, history, understand_level, retry=3):
    history = process_chat_history(history)
    prompt = prompts["spatial_selection"].format(understand_level=understand_level)
    return query_vlm(prompt, history, image, spatialSelectionOutput, retry)

