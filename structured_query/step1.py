from typing import List
from pydantic import BaseModel
from structured_query import query_llm, process_chat_history

prompts = {
    "scene_description": '''
    Your task is to decompose the story and scene described by the child into several describable 3D objects, and output them sequentially into a structured string list object_list[].
    For example, if the child says "The big-eyed monkey is climbing the tree", the output string list should be object_list=["Monkey, big-eyed, action is climbing", "Tree"].
    Please only decompose and output according to the child's description, without adding extra information or your own ideas. If the child's description is not detailed enough, output an empty string list object_list=[].
    The previous conversation history is as follows: 
    {chat_history}
    ''',
    "scene_optimization": '''
    Your task is to decompose the story and scene described by the child into several describable 3D objects, and output them sequentially into a structured string list object_list[].
    For example, if the child says "The big-eyed monkey is climbing the tree", the output string list should be object_list=["Monkey, big-eyed, action is climbing", "Tree"].
    Please only decompose and output according to the child's description, without adding extra information or your own ideas. If the child's description is not detailed enough, output an empty string list object_list=[].
    Now we already have the preliminary list information: {object_list}.
    You need to improve and supplement the entries in the list based on the new description or existing content.
    The previous conversation history is as follows:
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

