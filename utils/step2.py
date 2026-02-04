import json
import random
import streamlit as st
from langchain_community.chat_message_histories import ChatMessageHistory

history_store_step_2 = {}

def get_history_step_2(session_id: str):
    if session_id not in history_store_step_2:
        history_store_step_2[session_id] = ChatMessageHistory()
    return history_store_step_2[session_id]


class LearningStatus:
    def __init__(self, db="./database/spatial_dim.json"):
        self._load_db(db)
        self.num_dim = 8
        self.max_stage = 3
        self.learning_status = {}
        for i in range(self.num_dim):
            self.learning_status[i] = {
                "name": self.db[str(i)]["name"],
                "word_idx": 0,
                "stage": 0,
                "word_length": len(self.db[str(i)]["description"]),
                "done": False
            }
    
    def _load_db(self, db):
        with open(db, "r") as f:
            self.db = json.load(f)
        
    def proceed(self, dim_idx: int):
        if self.learning_status[dim_idx]["stage"] + 1 < self.max_stage:
            self.learning_status[dim_idx]["stage"] += 1
        else:
            if self.learning_status[dim_idx]["word_idx"] + 1 < self.learning_status[dim_idx]["word_length"]:
                self.learning_status[dim_idx]["word_idx"] += 1
                self.learning_status[dim_idx]["stage"] = 0
        return self.learning_status[dim_idx]
    
    def next(self, dim_idx: int):
        if self.learning_status[dim_idx]["word_idx"] + 1 < self.learning_status[dim_idx]["word_length"]:
            self.learning_status[dim_idx]["word_idx"] += 1
            self.learning_status[dim_idx]["stage"] = 0
        else:
            self.learning_status[dim_idx]["finished"] = True

    def read(self):
        return [int((self.learning_status[i]["word_idx"]+1)/self.learning_status[i]["word_length"]*100) for i in range(self.num_dim)]
    
    def get(self, dim_idx: int):
        return self.db[str(dim_idx)]["description"][self.learning_status[dim_idx]["word_idx"]], self.learning_status[dim_idx]["stage"]

class TutorialList:
    def __init__(self):
        self.tutorials = []
        self.current_tutorial = 0
        self.max_tutorial = 0
        self.finished = False
    
    def add(self, tutorial):
        self.tutorials.append(Tutorial(tutorial))
        self.max_tutorial += 1
    
    def get(self):
        return self.tutorials[self.current_tutorial].get()
    
    def current(self):
        return self.tutorials[self.current_tutorial]
    
    def proceed(self):
        if not self.tutorials[self.current_tutorial].finished:
            self.tutorials[self.current_tutorial].proceed()
    
    def next(self):
        if self.current_tutorial < self.max_tutorial - 1:
            self.current_tutorial += 1
        else:
            self.finished = True
                
            
class Tutorial:
    def __init__(self, instructions):
        self.instructions = instructions
        self.max_step = len(instructions)
        self.current_step = 1
        self.finished = False
    
    def get(self):
        return self.instructions[self.current_step-1]
    
    def proceed(self):
        if self.current_step + 1 <= self.max_step:
            self.current_step += 1
        else:
            self.finished = True


def configure_learning_status():
    if "learning_status" not in st.session_state:
        st.session_state["learning_status"] = LearningStatus()
    with st.sidebar:
        if "tutorial_list" in st.session_state:
            if st.session_state["tutorial_list"].finished:
                st.balloons()
                next_page = st.button("💪 Start interacting", use_container_width=True)
                if next_page:
                    st.switch_page("./pages/step3.py")
            elif st.session_state["tutorial_list"].current().finished:
                next_tutorial = st.button("👉 Next block", use_container_width=True)
                if next_tutorial:
                    st.session_state["tutorial_list"].next()
        st.markdown("### Current Progress")
        for idx, status in st.session_state["learning_status"].learning_status.items():
            col_1, col_2 = st.columns([2, 2])
            with col_1:
                st.markdown(f"**Dimension {idx+1}: {status['name']}**")
            with col_2:
                st.progress((status["word_idx"]+1)/status["word_length"])
            col_3, col_4 = st.columns([3, 2])
            with col_3:
                st.write(f"Vocabulary: *{st.session_state['learning_status'].db[str(idx)]['description'][status['word_idx']]}*")
            with col_4:
                st.button("✅ Learned", key=random.randint(100000,999999), on_click=proceed_status, args=(idx,), use_container_width=True)
            st.write("\n")
        st.divider()

def initialize_tutorial_list(instructions):
    configure_tutorial_list()
    st.session_state["tutorial_list"].add(instructions)

def configure_tutorial_list():
    if "tutorial_list" not in st.session_state:
        st.session_state["tutorial_list"] = TutorialList()

def proceed_status(idx):
    st.session_state["learning_status"].next(idx)