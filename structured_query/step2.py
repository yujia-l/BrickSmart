from typing import List
from pydantic import BaseModel
from structured_query import query_vlm, process_chat_history

prompts = {
    "spatial_selection": '''
    你是一个空间语言教师，你的职责是根据任务和学生情况判断该学习的空间语言任务。请根据以下信息：
    1. 根据提供的乐高拼装教程图片，详细分析并描述当前积木搭建任务，输出字符串参数 instruction：
        (1) 图片展示的乐高模型的整体构造和设计特点。
        (2) 识别并描述图片中出现的乐高零件种类及其颜色。
        (3) 指出图片中的拼装步骤，包括任何特别的组装技巧或需要特别注意的细节。
        (4) 使用专业的乐高术语来增加描述的准确性和专业性。
        (5) 确保输出的文字描述准确反映图片内容，语言表达清晰、专业、详细，便于读者理解拼装过程。
    2. 空间语言的8个维度包括：
        (1) 空间维度（大小、高低、长短、宽窄、薄厚、深浅）；
        (2) 形状（圆形、正方形、长方形、三角形、球形、圆柱形、圆锥形）；
        (3) 位置和方向（前后、左右、上下、里外、中间/旁边）；
        (4) 方向和变换（向左/向右、向前/向后、向上/向下）；
        (5) 连续量（整体、部分、几分之一、多数/少数）；
        (6) 指示词（这里、那里、哪里）；
        (7) 空间特征和属性（直线、曲线、圆形、角、点、平面、曲面）；
        (8) 模式（下一个、增加、减少）。
    3. 用户当前对空间语言的掌握程度是：{understand_level}，代表了8个维度分别的学习进度（以百分比表示）。
    判断最适合学习的3个空间语言类别，尽量挑选适合当前积木搭建任务且用户掌握程度不高的类别。
    输出长度为3的列表 spatial_list，每个元素的取值范围为0-7，代表空间语言类别的索引。
    '''
}


class spatialSelectionOutput(BaseModel):
    instruction: str
    spatial_list: List[int]


def spatial_selection(image, history, understand_level, retry=3):
    history = process_chat_history(history)
    prompt = prompts["spatial_selection"].format(understand_level=understand_level)
    return query_vlm(prompt, history, image, spatialSelectionOutput, retry)

