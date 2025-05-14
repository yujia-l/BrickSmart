from typing import List
from pydantic import BaseModel
from structured_query import query_llm, process_chat_history

prompts = {
    "scene_description": '''
    你的任务是孩子讲述的故事和场景分解成几个可描述的3D对象，并依次输出到结构化的字符串列表 object_list[] 中。
    例如，孩子说“大眼睛的猴子在爬树”，则输出字符串列表 object_list=["猴子，大眼睛，动作是正在爬树", "树"]。
    请你仅按照孩子的描述来分解和输出，不要添加额外的信息或者自己的想法。如果孩子描述的内容不够详细，则输出空白字符串列表 object_list=[]。
    之前的对话历史如下： 
    {chat_history}
    ''',
    "scene_optimization": '''
    你的任务是孩子讲述的故事和场景分解成几个可描述的3D对象，并依次输出到结构化的字符串列表 object_list[] 中。
    例如，孩子说“大眼睛的猴子在爬树”，则输出字符串列表 object_list=["猴子，大眼睛，动作是正在爬树", "树"]。
    请你仅按照孩子的描述来分解和输出，不要添加额外的信息或者自己的想法。如果孩子描述的内容不够详细，则输出空白字符串列表 object_list=[]。
    现在已经有了初步的列表信息：{object_list}。
    你需要根据新的描述或者已有内容，完善和补充列表中的条目。
    之前的对话历史如下： 
    {chat_history}
    '''
}


class sceneDescriptionOutput(BaseModel):
    object_list: List[str]


def process_object_list(object_list):
    output = ''''''   
    for idx, obj in enumerate(object_list):
        output += f'''object_list[{idx}]="{obj}"\n'''
    return output

def scene_description(history, objects, retry=3):
    history = process_chat_history(history)
    if objects:
        objects = process_object_list(objects)
        prompt = prompts["scene_optimization"].format(object_list=objects, chat_history=history)
    else:
        prompt = prompts["scene_description"].format(chat_history=history)

    return query_llm(prompt, history, sceneDescriptionOutput, retry)

