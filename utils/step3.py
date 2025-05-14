from langchain_community.chat_message_histories import ChatMessageHistory

history_store_step_3 = {}

def get_history_step_3(session_id: str):
    if session_id not in history_store_step_3:
        history_store_step_3[session_id] = ChatMessageHistory()
    return history_store_step_3[session_id]