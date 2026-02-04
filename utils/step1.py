import streamlit as st
from langchain_community.chat_message_histories import ChatMessageHistory
import requests
from utils.step2 import initialize_tutorial_list

history_store_step_1 = {}
object_db = {}

def get_history_step_1(session_id: str):
    if session_id not in history_store_step_1:
        history_store_step_1[session_id] = ChatMessageHistory()
    return history_store_step_1[session_id]


def configure_objects():
    st.sidebar.divider()
    st.sidebar.markdown("### Block Info")
    if "object_list" in st.session_state:
        object_list = st.session_state["object_list"]
        if object_list:
            for idx, obj in enumerate(object_list):
                st.sidebar.write(f"🧩 {obj}")
                if obj in object_db.keys():
                    st.sidebar.image(object_db[obj]['rendered_image_url'])
                else:
                    with st.status(f"🧩 Generating blocks...（{idx+1}/{len(object_list)}）"):
                        obj_json = requests.post('http://47.251.27.187/model/', json={'prompt': obj}).json()
                        st.sidebar.image(obj_json['rendered_image_url'])
                    object_db[obj] = obj_json
                    
            next_page = st.sidebar.button("💪 Start building", use_container_width=True)
            if next_page:
                for idx, obj in enumerate(object_list):
                    with st.status(f"🧩 Voxelizing blocks...（{idx+1}/{len(object_list)}）"):
                        if obj in object_db.keys():
                            obj_id = object_db[obj]['task_id']
                        else:
                            obj_id = requests.post('http://47.251.27.187/model/', json={'prompt': obj}).json()['task_id']
                        try:
                            voxel_id = requests.post('http://47.251.27.187/voxel/', json={"task_id": obj_id}).json()['task_id']
                            tutorials = requests.post('http://47.251.27.187/lego_tutorial/', json={"task_id": voxel_id}).json()['instructions']
                            initialize_tutorial_list(tutorials)
                        except Exception as e:
                            print(e)
                            st.sidebar.error(f"Failed to voxelize block model: “{obj}”, please try again later")
                st.switch_page("./pages/step2.py")

        else:
            st.session_state["object_picture_list"] = None
            st.sidebar.write("🧩 Please continue the conversation to improve block information")
    else:
        st.sidebar.write("🧩 Please continue the conversation to improve block information")