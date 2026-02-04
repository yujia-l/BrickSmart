import utils
import streamlit as st
from streamlit_mic_recorder import speech_to_text
from streaming import StreamHandler

from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from utils.step1 import get_history_step_1, configure_objects
from structured_query.step1 import process_object_list, scene_description

st.set_page_config(page_title="BrickSmart", page_icon="🧱")
st.header('BrickSmart - Scenario Description')
with st.sidebar:
    st.page_link("home.py", label='Homepage', icon="🏠", use_container_width=True)
    st.divider()

prompts ={
    "scene_description": '''
    As a specialized intelligent assistant to help parents interact with their children, your task is to guide children to describe in detail the scenes they like in their minds, providing a clear visual basis for LEGO building (even though you do not directly participate in the building process).
    In the conversation, you need to actively encourage children to explore and describe every detail of the scene, including the layout of the environment, the characters in the scene, and the props used.
    You should continuously ask specific guiding questions and suggestions to help parents make children's descriptions clearer and more specific.
    ''',
    "scene_optimization": '''
    As a specialized intelligent assistant to help parents interact with their children, your task is to guide children to describe in detail the scenes they like in their minds, providing a clear visual basis for LEGO building (even though you do not directly participate in the building process).
    In the conversation, you need to actively encourage children to explore and describe every detail of the scene, including the layout of the environment, the characters in the scene, and the props used.
    You should continuously ask specific guiding questions and suggestions to help parents make children's descriptions clearer and more specific.
    For example, ask about the specific colors and materials of an object, or the actions and expressions of a character, to stimulate the child's imagination and help them refine their LEGO creations.
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
            start_prompt="🎙️ Voice input",
            stop_prompt="🎙️ Input finished",
            just_once=True,
            use_container_width=True,
            callback=utils.stt_callback,
            args=(),
            kwargs={},
            key=None
        )
        user_query = st.chat_input("You can click the button above for voice input or enter text here")

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