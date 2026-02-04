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
st.header('BrickSmart - Block building')
with st.sidebar:
    st.page_link("home.py", label='Homepage', icon="🏠", use_container_width=True)
    st.page_link("./pages/step1.py", label='Scene Description', icon="💬", use_container_width=True)
    # st.page_link("./pages/step3.py", label='xxx', use_container_width=True) # to be deleted after debugging
    st.divider()

stages = ["Noun explanation, explaining the meaning of vocabulary", "Contextual application, using the vocabulary in the current LEGO building activity", "Questioning and testing, examining and deepening the child's understanding and application of vocabulary through questioning"]

prompts ={
    "spatial_selection": '''
    You are a family guide, and your responsibility is to help parents guide their children and enhance their spatial language skills. You need to generate guiding prompts for parents in real-time based on the steps of the current LEGO building tutorial.
    The spatial vocabulary that needs to be learned and the corresponding stages include：
    1. Vocabulary: {word_1}, Learning Stage: {stage_1};
    2. Vocabulary: {word_2}, Learning Stage: {stage_2};
    3. Vocabulary: {word_3}, Learning Stage: {stage_3};
    The current LEGO building tutorial is: {instruction}. The image includes a top view - the LEGO bricks to be built in the current step, and a whole view - containing the current task and all previously built parts.
    Please understand the current building task, and generate prompts and examples for parents to help children learn the above three vocabulary words, each corresponding to its learning stage.
    Example output format:
    1. Vocabulary: Circle, Learning Stage: Noun explanation
    Prompt: You can tell the child that a circle is a shape with no corners, and the distance from every point on the edge to the center is the same.
    Example: During the building process, you can find circular LEGO pieces or circular patterns on the pieces to help them understand.
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
                        st.session_state[st.session_state["current_page"]]["messages"].append({"role": "assistant", "content": "You have completed the current LEGO building task. Click the sidebar button to continue to the next one!"})
            # Jump to the next page if the tutorial is finished
            if st.session_state["tutorial_list"].finished:
                st.session_state[st.session_state["current_page"]]["messages"].append({"role": "assistant", "content": "🎉 Congratulations on completing the LEGO building! Click the sidebar button to start interacting!"})
            st.rerun()  # Rerun the app to update the chat

if __name__ == "__main__":
    obj = ChatBotForTutorial()
    obj.main()
