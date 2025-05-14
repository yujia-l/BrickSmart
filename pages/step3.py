import utils
import streamlit as st

from structured_query import simple_query

st.set_page_config(page_title="BrickSmart", page_icon="🧱")
st.header('BrickSmart - 积木组合')
with st.sidebar:
    st.page_link("home.py", label='主页', icon="🏠", use_container_width=True)
    st.page_link("./pages/step1.py", label='场景描述', icon="💬", use_container_width=True)
    st.page_link("./pages/step2.py", label='积木搭建', icon="🧩", use_container_width=True)
    st.divider()

prompts = '''
你是一个帮助家长与孩子互动的助手，目标是提升孩子的空间语言表达能力。孩子和家长当前使用乐高积木搭建了几个乐高模型，包括：{objects}。
你的任务是引导家长和孩子，通过让这些乐高模型“动起来”来描述它们的状态，从而增强孩子对空间概念的理解。家长可以移动搭建好的上述乐高模型，或乐高积木，并让孩子描述这些动作。
请按照以下格式输出互动建议：
词汇：要学习的空间语言词汇\n
动态指令例子：给出移动物体的具体方法\n
家长引导语示例：提供家长可以使用的引导语

示例格式输出：
1. 词汇：向左/向右\n
动态指令例子：让小人向前走，然后向左转\n
家长引导语示例：你看这个可爱的小人，他往前走，然后向左转啦。你能让小人向右转吗？

针对下列 {num_words} 个关键词：{keywords}，逐个输出互动建议。
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
