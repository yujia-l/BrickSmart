import os
import openai
import random
import pandas as pd
import streamlit as st
from datetime import datetime
from streamlit.logger import get_logger
from langchain_openai import ChatOpenAI
from streamlit_gsheets import GSheetsConnection

from utils.step2 import LearningStatus

logger = get_logger('Langchain-Chatbot')

# set the openai api key as the environment variable
if os.path.exists("./openai.key"):
    os.environ["OPENAI_API_KEY"] = open("./openai.key").read().strip()
else:
    os.environ['OPENAI_API_KEY'] = st.secrets['OPENAI_KEY']

def welcome_message(page):
    if page == "ChatBotForSceneDescription":
        return "Hello! I'm BrickSmart, and I will help you guide your child to describe their favorite scenes."
    elif page == "ChatBotForTutorial":
        return "Hello! I'm BrickSmart, and I will help you guide your child to build their own LEGO bricks."
    elif page == "ChatBotForInteraction":
        return "Hello! I'm BrickSmart, and I will help you guide your child to interact with the built LEGO bricks."

def write_google_sheet(session_id: str):
    conn = st.connection("gsheets", type=GSheetsConnection)
    if "df" not in st.session_state:
        try:
            df = conn.read(worksheet=session_id)
        except:
            df = conn.create(worksheet=session_id, data=pd.DataFrame(columns=["idx", "timestamp", "role", "content"]))
        st.session_state["df"] = df
    df = st.session_state["df"]
    df.loc[len(df)] = {"idx": len(df), "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "role": st.session_state["messages"][-1]["role"], "content": st.session_state["messages"][-1]["content"]}
    conn.update(worksheet=session_id, data=df)    

#decorator
def enable_chat_history(func):
    if os.environ.get("OPENAI_API_KEY"):
        current_page = func.__qualname__ 
        st.session_state["current_page"] = str(current_page)

        # to show chat history on ui
        if st.session_state["current_page"] not in st.session_state:
            st.session_state[st.session_state["current_page"]] = {}
            st.session_state[st.session_state["current_page"]]["messages"] = [{"role": "assistant", "content": welcome_message(current_page.split(".")[0])}]
        for msg in st.session_state[st.session_state["current_page"]]["messages"]:
            if msg["role"] == "assistant":
                st.chat_message(msg["role"], avatar="./assets/avatar.jpg").write(msg["content"])
            elif msg["role"] == "image":
                st.image(msg["content"], use_column_width=True)
            else:
                st.chat_message(msg["role"]).write(msg["content"])
        
        # to access the global variable
        if "object_list" not in st.session_state:
            st.session_state["object_list"] = None
        if "learning_status" not in st.session_state:
            st.session_state["learning_status"] = LearningStatus()

    def execute(*args, **kwargs):
        func(*args, **kwargs)
    return execute

#decorator
def access_global_var(func):
    def execute(*args, **kwargs):
        global history_store_step_1
        return func(*args, **kwargs)
    return execute

def display_msg(msg, author):
    """Method to display message on the UI

    Args:
        msg (str): message to display
        author (str): author of the message -user/assistant
    """
    st.session_state[st.session_state["current_page"]]["messages"].append({"role": author, "content": msg})
    st.chat_message(author, avatar="./assets/avatar.jpg").write(msg) if author == "assistant" else st.chat_message(author).write(msg)

def choose_custom_openai_key():
    openai_api_key = st.sidebar.text_input(
        label="OpenAI API Key",
        type="password",
        placeholder="sk-...",
        key="SELECTED_OPENAI_API_KEY"
        )
    if not openai_api_key:
        st.error("Please add your OpenAI API key to continue.")
        st.info("Obtain your key from this link: https://platform.openai.com/account/api-keys")
        st.stop()

    model = "gpt-4o-mini"
    try:
        client = openai.OpenAI(api_key=openai_api_key)
        available_models = [{"id": i.id, "created":datetime.fromtimestamp(i.created)} for i in client.models.list() if str(i.id).startswith("gpt")]
        available_models = sorted(available_models, key=lambda x: x["created"])
        available_models = [i["id"] for i in available_models]

        model = st.sidebar.selectbox(
            label="Model",
            options=available_models,
            key="SELECTED_OPENAI_MODEL"
        )
    except openai.AuthenticationError as e:
        st.error(e.body["message"])
        st.stop()
    except Exception as e:
        print(e)
        st.error("Something went wrong. Please try again later.")
        st.stop()
    return model, openai_api_key

def print_qa(cls, question, answer):
    log_str = "\nUsecase: {}\nQuestion: {}\nAnswer: {}\n" + "------"*10
    logger.info(log_str.format(cls.__name__, question, answer))

def sync_st_session():
    for k, v in st.session_state.items():
        st.session_state[k] = v

def stt_callback():
    if "stt_output" not in st.session_state:
        st.session_state.stt_output = ""
    st.write(st.session_state.stt_output)

# For homepage
def configure_user_session():
    if "SESSION_ID" not in st.session_state:
        # let user input a number as the session id
        session_id = st.sidebar.text_input("Session ID", key="SESSION_ID", disabled=(True if "session_id" in st.session_state else False))
        if not session_id:
            if "session_id" not in st.session_state:
                # if the user does not input a session id, generate a random one
                session_id = str(random.randint(100000,999999))
                st.session_state["session_id"] = session_id
            else:
                session_id = st.session_state["session_id"]
        else:
            st.session_state["session_id"]  = session_id
    else:
        session_id = st.session_state["session_id"]
    st.sidebar.markdown("### Conversation info")
    st.sidebar.write(f"Session ID: {session_id}")
    return session_id

def configure_llm():
    available_llms = ["gpt-4o-mini","use your openai api key"]
    if "SELECTED_LLM" not in st.session_state:
        llm_opt = st.sidebar.radio(
            label="LLM",
            options=available_llms,
            key="SELECTED_LLM"
            )
    else:
        llm_opt = st.session_state["SELECTED_LLM"]

    if llm_opt == "gpt-4o-mini":
        llm = ChatOpenAI(model_name=llm_opt, temperature=0, streaming=True, api_key=os.environ.get("OPENAI_API_KEY"))
    else:
        model, openai_api_key = choose_custom_openai_key()
        llm = ChatOpenAI(model_name=model, temperature=0, streaming=True, api_key=openai_api_key)
    return llm
