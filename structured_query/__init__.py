import base64
import streamlit as st
from openai import OpenAI

client = OpenAI(api_key=st.secrets['OPENAI_KEY'].strip())

def process_chat_history(chat_history):
    output = ''''''
    for chat in chat_history:
        output += f'''{chat['role']}: {chat['content']}\n'''
    return output

def encode_image(image_path):
    try:
        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            return f"data:image/jpeg;base64,{base64_image}"
    except:
        # load image from URL
        return image_path

def simple_query(prompt, retry=3):
    while retry > 0:
        try:
            completion = client.chat.completions.create(
                model="gpt-4o-2024-08-06",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "请告诉我怎么引导孩子用搭建好的乐高模型互动。"},
                ],
            )
            output = completion.choices[0].message.content
            return output
        except Exception as e:
            retry -= 1
            if retry == 0:
                raise e

def query_llm(prompt, history, format, retry=3):
    while retry > 0:
        try:
            completion = client.beta.chat.completions.parse(
                model="gpt-4o-2024-08-06",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": history},
                ],
                response_format = format,
            )
            output = completion.choices[0].message.parsed
            return output
        except Exception as e:
            retry -= 1
            if retry == 0:
                raise e

def query_vlm(prompt, history, image, format, retry=3):
    image_url = encode_image(image)
    while retry > 0:
        try:
            completion = client.beta.chat.completions.parse(
                model="gpt-4o-2024-08-06",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": history},
                        {"type": "image_url", "image_url": { 
                            "url": image_url
                            }
                        }
                    ]
                    },
                ],
                response_format = format,
            )
            output = completion.choices[0].message.parsed
            return output
        except Exception as e:
            retry -= 1
            if retry == 0:
                raise e