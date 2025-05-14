import utils
import streamlit as st
from streamlit_mic_recorder import speech_to_text
from streaming import StreamHandler

from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from utils.step1 import get_history_step_1, configure_objects
from structured_query.step1 import process_object_list, scene_description

st.set_page_config(page_title="BrickSmart", page_icon="🧱")
st.header('BrickSmart - 场景描述')
with st.sidebar:
    st.page_link("home.py", label='主页', icon="🏠", use_container_width=True)
    st.divider()

prompts ={
    "scene_description": '''
    作为专门帮助家长与孩子进行互动的智能助手，你的任务是引导孩子详细描述他们心中喜欢的场景，为乐高搭建提供清晰的视觉基础（尽管你不直接参与搭建过程）。
    在对话中，你需要积极鼓励孩子探索并详细描述场景中的每一个细节，包括环境布局、场景中的角色，以及使用的道具。
    你应持续提出具体的引导问题和建议，帮助家长使孩子的描述更加清晰和具体。
    ''',
    "scene_optimization": '''
    作为专门帮助家长与孩子进行互动的智能助手，你的任务是引导孩子详细描述他们心中喜欢的场景，为乐高搭建提供清晰的视觉基础（尽管你不直接参与搭建过程）。
    在对话中，你需要积极鼓励孩子探索并详细描述场景中的每一个细节，包括环境布局、场景中的角色，以及使用的道具。
    利用已经从之前的对话中整理出的对象列表{object_list}，你应持续提出具体的引导问题和建议，帮助家长使孩子的描述更加清晰和具体。
    例如，询问关于某个物体的具体颜色和材料，或者角色的动作表情，以此来激发孩子的想象力，并且更精细地构想他们的乐高作品。
    '''
}

def get_prompt(object_list=None):
    if not object_list:
        return ChatPromptTemplate.from_messages(
            [
                ("system", prompts["scene_description"]),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
            ]
        )
    else:
        return ChatPromptTemplate.from_messages(
            [
                ("system", prompts["scene_optimization"].format(object_list=process_object_list(object_list))),
                MessagesPlaceholder("chat_history"),
                ("human", "{input}"),
            ]
        )


print("********** Starting the ChatBotForSceneDescription **********")


class ChatBotForSceneDescription:
    def __init__(self):
        utils.sync_st_session()
        self.session_id = utils.configure_user_session()
        self.llm = utils.configure_llm()
        configure_objects()
        

    @utils.access_global_var
    def setup_chain(self, object_list=None):
        self.chain = get_prompt(object_list) | self.llm
        self.conversational_chain = RunnableWithMessageHistory(
            self.chain,
            get_history_step_1,
            input_messages_key="input",
            history_messages_key="chat_history",
        )

        return self.conversational_chain
    
    @utils.enable_chat_history
    def main(self):
        audio_input = speech_to_text(
            language='zh-CN',
            start_prompt="🎙️ 语音输入",
            stop_prompt="🎙️ 输入完毕",
            just_once=True,
            use_container_width=True,
            callback=utils.stt_callback,
            args=(),
            kwargs={},
            key=None
        )
        user_query = st.chat_input("你可以点击上方按钮语音输入，或者在此处输入文字")

        # Insert the audio input into the chat input box
        js = f"""
            <script>
                function insertText(dummy_var_to_force_repeat_execution) {{
                    var chatInput = parent.document.querySelector('textarea[data-testid="stChatInputTextArea"]');
                    var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
                    nativeInputValueSetter.call(chatInput, "{audio_input if audio_input else ""}");
                    var event = new Event('input', {{ bubbles: true}});
                    chatInput.dispatchEvent(event);
                }}
                insertText({len(st.session_state[st.session_state["current_page"]]["messages"])});
            </script>
            """
        st.components.v1.html(js)

        if user_query:
            utils.display_msg(user_query, 'user')
            object_list = scene_description(st.session_state[st.session_state["current_page"]]["messages"], st.session_state.object_list).object_list
            st.session_state.object_list = object_list
            chain = self.setup_chain(object_list=st.session_state.object_list)

            with st.chat_message("assistant", avatar="./assets/avatar.jpg"):
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
                st.write(response)
                st.rerun()  # Rerun the app to update the chat

if __name__ == "__main__":
    obj = ChatBotForSceneDescription()
    obj.main()