import utils
from PIL import Image
from numpy import asarray
import streamlit as st
from streaming import StreamHandler

from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from utils.step2 import get_history_step_2, configure_learning_status, configure_tutorial_list
from structured_query.step2 import spatial_selection

import requests

st.set_page_config(page_title="BrickSmart", page_icon="🧱")
st.header('BrickSmart - 积木搭建')
with st.sidebar:
    st.page_link("home.py", label='主页', icon="🏠", use_container_width=True)
    st.page_link("./pages/step1.py", label='场景描述', icon="💬", use_container_width=True)
    # st.page_link("./pages/step3.py", label='xxx', use_container_width=True) # to be deleted after debugging
    st.divider()

stages = ["名词解释，解释词汇的意义", "情景运用，在当前积木搭建活动中使用该词汇", "提问检验，通过提问正在做的事情来检验和深化孩子对词汇的理解和应用能力"]

prompts ={
    "spatial_selection": '''
    你是一个家庭引导师，你的职责是帮助家长引导孩子并提升空间语言能力。你需要根据目前乐高搭建教程的步骤，实时为家长生成引导提示。
    当前需要学习的空间词汇和对应的阶段包括：
    1. 词汇：{word_1}，学习阶段：{stage_1}；
    2. 词汇：{word_2}，学习阶段：{stage_2}；
    3. 词汇：{word_3}，学习阶段：{stage_3}；
    当前乐高搭建的教程为：{instruction}，图片中包含俯视图（top view）-为当前步骤要搭建的积木块，和整体视图（whole view）-包含当前任务和之前已搭建好的所有。
    请理解当前的搭建任务，在引导搭建孩子的过程中学习以上三个词汇，分别符合对应的学习阶段，为家长生成提示和举例。
    示例格式输出：
    1. 词汇：圆形，学习阶段：名词解释
    提示：可以告诉孩子，圆形是一种没有角的形状，边上的每一点到中心点的距离都是一样的。
    示例：在搭建过程中可以找到圆形的积木块，或者积木块上的圆形图案，帮助他们理解。
    '''
}

def get_prompt(instruction, spatial_idx):
    word_list = [st.session_state["learning_status"].get(idx)[0] for idx in spatial_idx]
    stage_list = [stages[st.session_state["learning_status"].get(idx)[1]] for idx in spatial_idx]
    return ChatPromptTemplate.from_messages(
        [
            ("system", prompts["spatial_selection"].format(instruction=instruction, word_1=word_list[0], stage_1=stage_list[0], word_2=word_list[1], stage_2=stage_list[1], word_3=word_list[2], stage_3=stage_list[2])),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )


print("********** Starting the ChatBotForTutorial **********")


class ChatBotForTutorial:
    def __init__(self):
        utils.sync_st_session()
        configure_learning_status()
        configure_tutorial_list()
        self.session_id = utils.configure_user_session()
        self.llm = utils.configure_llm()

    @utils.access_global_var
    def setup_chain(self, instruction, spatial_idx):
        self.chain = get_prompt(instruction, spatial_idx) | self.llm
        self.conversational_chain = RunnableWithMessageHistory(
            self.chain,
            get_history_step_2,
            input_messages_key="input",
            history_messages_key="chat_history",
        )

        return self.conversational_chain
    
    @utils.enable_chat_history
    def main(self):
        user_query = st.chat_input()

        try:
            first_step =  st.session_state["tutorial_list"].current().current_step == 1
        except:
            first_step = False

        if user_query or first_step:
            if user_query:
                utils.display_msg(user_query, 'user')
            if not st.session_state["tutorial_list"].finished:
                # tutorial_step =  st.session_state["tutorial_step"].get()
                # image_path = "./instructions/step_{}.png".format(tutorial_step)
                image_path = st.session_state["tutorial_list"].get()
                instructions = spatial_selection(image=image_path, history=st.session_state[st.session_state["current_page"]]["messages"], understand_level=st.session_state["learning_status"].read())
                instruction = instructions.instruction
                spatial_list = instructions.spatial_list
                chain = self.setup_chain(instruction, spatial_list)
            
                with st.chat_message("assistant", avatar="./assets/avatar.jpg"):
                    # image = asarray(Image.open(image_path))
                    st.image(image_path, use_column_width=True)
                    st.session_state[st.session_state["current_page"]]["messages"].append({"role": "image", "content": image_path})
                    st_cb = StreamHandler(st.empty())
                    result = chain.invoke(
                        input = {
                            "input": user_query,
                            },
                        config = {
                            "configurable": {"session_id": self.session_id}, 
                            "callbacks": [st_cb]
                            }
                    )
                    response = result.content
                    st.session_state[st.session_state["current_page"]]["messages"].append({"role": "assistant", "content": response})
                    for idx in spatial_list:
                        st.session_state["learning_status"].proceed(idx)
                    st.session_state["tutorial_list"].proceed()
                    if st.session_state["tutorial_list"].current().finished:
                        st.session_state[st.session_state["current_page"]]["messages"].append({"role": "assistant", "content": "你已经完成了当前积木的搭建，点击侧栏按钮，让我们继续下一个吧！"})
            # Jump to the next page if the tutorial is finished
            if st.session_state["tutorial_list"].finished:
                st.session_state[st.session_state["current_page"]]["messages"].append({"role": "assistant", "content": "🎉 恭喜你完成了积木搭建，点击侧栏按钮开始互动！"})
            st.rerun()  # Rerun the app to update the chat

if __name__ == "__main__":
    obj = ChatBotForTutorial()
    obj.main()
