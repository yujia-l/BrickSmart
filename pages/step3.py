import utils
import streamlit as st

from structured_query import simple_query

st.set_page_config(page_title="BrickSmart", page_icon="🧱")
st.header('BrickSmart - Block Interaction')
with st.sidebar:
    st.page_link("home.py", label='Homepage', icon="🏠", use_container_width=True)
    st.page_link("./pages/step1.py", label='Scene Description', icon="💬", use_container_width=True)
    st.page_link("./pages/step2.py", label='Block Building', icon="🧩", use_container_width=True)
    st.divider()

prompts = '''
You are a helper for parents to interact with their children, aiming to enhance children's spatial language skills. The child and parent are currently using LEGO bricks to build several LEGO models, including: {objects}.
Your task is to guide parents and children to describe the state of these LEGO models by making them "move", thereby enhancing the child's understanding of spatial concepts. Parents can move the built LEGO models or LEGO bricks and ask the child to describe these actions.
Please output interactive suggestions in the following format:
Vocabulary: The spatial language vocabulary to be learned\n
Dynamic instruction example: Give specific methods for moving objects\n
Parental guidance example: Provide guiding language that parents can use

Example output format:
1. Vocabulary: Left/Right\n
Dynamic instruction example: Move the little person forward, then turn left\n
Parental guidance example: Look at this cute little person, he moves forward and then turns left. Can you make the little person turn right?

For the following {num_words} keywords: {keywords}, please output interactive suggestions one by one.
'''

def get_prompt():
    if "object_list" in st.session_state:
        try:
            objects = "； ".join(st.session_state.object_list)
        except:
            objects = "none"
    else:
        raise ValueError("Object list not found in session state")
    keywords = []
    if "learning_status" in st.session_state:
        for idx, status in st.session_state["learning_status"].learning_status.items():
            if not status["done"]:
                current_word_idx = status["word_idx"]
                keywords += st.session_state["learning_status"].db[str(idx)]["description"][current_word_idx:]
    else:
        raise ValueError("Learning status not found in session state")
    return prompts.format(objects=objects, num_words=len(keywords), keywords="、 ".join(keywords))


print("********** Starting the ChatBotForInteraction **********")


class ChatBotForInteraction:
    def __init__(self):
        utils.sync_st_session()
        self.session_id = utils.configure_user_session()
        self.llm = utils.configure_llm()
    
    @utils.enable_chat_history
    def main(self):
        with st.chat_message("assistant", avatar="./assets/avatar.jpg"):
            response = simple_query(get_prompt())
            st.session_state[st.session_state["current_page"]]["messages"].append({"role": "assistant", "content": response})
            st.write(response)

if __name__ == "__main__":
    obj = ChatBotForInteraction()
    obj.main()
