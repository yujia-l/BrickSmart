# BrickSmart - Comprehensive Codebase Analysis

## 1. Project Overview

**BrickSmart** is a Streamlit-based educational web application that helps parents guide children through LEGO building activities while teaching **spatial language** concepts. It leverages AI (OpenAI GPT-4o) to provide interactive, conversational guidance across a 3-step workflow:

1. **Scene Description** - Children describe scenes they want to build
2. **Block Building** - Step-by-step LEGO building tutorials with spatial vocabulary learning
3. **Block Interaction** - Interactive activities to reinforce spatial language concepts using the built models

---

## 2. Folder Structure

```
BrickSmart/
├── .streamlit/                     # Streamlit configuration
│   └── secrets.toml                # API keys (OPENAI_KEY)
├── __pycache__/                    # Python bytecode cache
├── assets/
│   └── avatar.jpg                  # Chat assistant avatar image
├── database/
│   └── spatial_dim.json            # Spatial language vocabulary database (8 dimensions)
├── instructions/
│   └── step_1.png ... step_10.png  # LEGO building tutorial step images
├── pages/                          # Streamlit multi-page app pages
│   ├── step1.py                    # Page: Scene Description
│   ├── step2.py                    # Page: Block Building
│   └── step3.py                    # Page: Block Interaction
├── structured_query/               # Structured LLM query modules
│   ├── __init__.py                 # Core LLM/VLM query functions + OpenAI client
│   ├── step1.py                    # Scene description structured queries
│   └── step2.py                    # Spatial selection structured queries
├── utils/                          # Utility modules
│   ├── __init__.py                 # Re-exports from utils.py
│   ├── utils.py                    # Core utilities (LLM config, session, chat history)
│   ├── step1.py                    # Step 1 utilities (object management, API calls)
│   ├── step2.py                    # Step 2 utilities (learning status, tutorials)
│   └── step3.py                    # Step 3 utilities (chat history)
├── home.py                         # Main entry point / homepage
├── streaming.py                    # LangChain StreamHandler for real-time LLM output
├── requirements.txt                # Python dependencies
└── README.md                       # Project README (minimal)
```

---

## 3. Tech Stack

| Category | Technology | Version |
|----------|-----------|---------|
| **Web Framework** | Streamlit | 1.37.1 |
| **LLM Orchestration** | LangChain | 0.2.9 |
| **AI Models** | OpenAI GPT-4o-2024-08-06 | (structured queries) |
| **AI Models** | OpenAI GPT-4o-mini | (conversational chat) |
| **LLM Client** | langchain-openai | 0.1.17 |
| **OpenAI SDK** | openai | 1.41.0 |
| **Database ORM** | SQLAlchemy | 2.0.31 |
| **Data Validation** | Pydantic | (via LangChain) |
| **Image Processing** | Pillow (PIL) | < 11 |
| **Data Handling** | pandas, numpy | < 2.0.0 |
| **Voice Input** | streamlit-mic-recorder | latest |
| **Google Sheets** | st-gsheets-connection | latest |
| **Web Search** | duckduckgo-search | 6.2.1 |
| **PDF Processing** | pypdf | 4.3.0 |
| **Embeddings** | fastembed | latest |

---

## 4. Architecture & Data Flow

### 4.1 High-Level Flow

```
Homepage (home.py)
    │
    ├── Configure Session ID (random 6-digit or user-provided)
    ├── Configure LLM (gpt-4o-mini or custom API key)
    └── "Click here to start!" → Step 1
         │
         Step 1: Scene Description (pages/step1.py)
         │   ├── Chat interface (text + voice input in Chinese)
         │   ├── AI guides child to describe scenes in detail
         │   ├── Structured query extracts objects from conversation
         │   ├── External API generates LEGO model previews
         │   └── "Start building" → Voxelize models → Step 2
         │
         Step 2: Block Building (pages/step2.py)
         │   ├── Step-by-step LEGO tutorial display (images)
         │   ├── AI generates spatial language learning prompts
         │   ├── 3 vocabulary words per step, each with learning stage
         │   ├── Progress tracking across 8 spatial dimensions
         │   └── "Start interacting" → Step 3
         │
         Step 3: Block Interaction (pages/step3.py)
             ├── AI generates interactive suggestions
             ├── Dynamic instructions for moving LEGO models
             └── Parental guidance examples for spatial vocabulary
```

### 4.2 AI Processing Pipeline

```
User Input → Structured Query (GPT-4o) → Extract Objects/Spatial Info
                                              ↓
                                   Chat Chain (GPT-4o-mini) → Streaming Response
                                              ↓
                                   Display in Streamlit UI
```

---

## 5. Detailed Component Analysis

### 5.1 Entry Point: `home.py`

- Sets page config (title: "BrickSmart", icon: brick emoji, layout: wide)
- Calls `configure_user_session()` - creates/manages session IDs
- Calls `configure_llm()` - lets user pick GPT-4o-mini or enter custom API key
- Provides a link to Step 1 to begin the workflow

### 5.2 Page: Step 1 - Scene Description (`pages/step1.py`)

**Class: `ChatBotForSceneDescription`**

- **Purpose**: Guide children to describe scenes they want to build with LEGO
- **Input Methods**:
  - Text chat input
  - Voice input (Chinese language, `zh-CN`) via `speech_to_text`
  - JavaScript injection auto-fills voice transcription into chat input
- **AI Behavior**:
  - Uses two prompt modes:
    - `scene_description`: Initial scene exploration (encourages detail about layout, characters, props)
    - `scene_optimization`: Refinement mode when objects are already extracted (asks about colors, materials, actions)
  - Each user message triggers a **structured query** (`scene_description()`) that extracts a list of 3D objects from the conversation using GPT-4o
  - Object list is stored in `st.session_state.object_list`
- **Sidebar Features**:
  - Displays extracted objects with LEGO model preview images (fetched from external API)
  - "Start building" button triggers model voxelization and tutorial generation
- **LangChain Setup**:
  - Uses `RunnableWithMessageHistory` for conversation continuity
  - `ChatPromptTemplate` with system prompt + chat history + user input
  - `StreamHandler` for real-time token streaming
- **External API Calls** (via `utils/step1.py`):
  - `POST http://47.251.27.187/model/` - Generate 3D LEGO model from text prompt
  - `POST http://47.251.27.187/voxel/` - Convert model to voxel format
  - `POST http://47.251.27.187/lego_tutorial/` - Generate step-by-step building instructions

### 5.3 Page: Step 2 - Block Building (`pages/step2.py`)

**Class: `ChatBotForTutorial`**

- **Purpose**: Guide parents through step-by-step LEGO building while teaching spatial vocabulary
- **Key Features**:
  - Displays tutorial images (top view + whole view of current building step)
  - Each step selects 3 spatial vocabulary words for learning
  - Each vocabulary has 3 learning stages:
    1. **Noun explanation** - defining the vocabulary
    2. **Contextual application** - using it in current LEGO building
    3. **Questioning and testing** - deepening understanding
  - Spatial dimension selection is AI-driven via `spatial_selection()` (uses GPT-4o with vision to analyze tutorial images)
- **Sidebar Features**:
  - Progress bars for all 8 spatial dimensions
  - Current vocabulary word display
  - "Learned" buttons to advance vocabulary progress
  - "Next block" / "Start interacting" navigation buttons
- **Flow**:
  - Auto-triggers on first step of each tutorial
  - Shows tutorial image → AI generates parental guidance → user responds → advance tutorial step
  - When all tutorials complete, navigates to Step 3

### 5.4 Page: Step 3 - Block Interaction (`pages/step3.py`)

**Class: `ChatBotForInteraction`**

- **Purpose**: Generate interactive activities to reinforce spatial language using built LEGO models
- **Key Features**:
  - Uses `simple_query()` (direct GPT-4o call, no LangChain chain) to generate interaction suggestions
  - Takes remaining unlearned vocabulary from all dimensions
  - Generates structured output with:
    - Vocabulary word
    - Dynamic instruction example (how to physically move the LEGO model)
    - Parental guidance example (what to say to the child)
- **Input**: Object list + remaining keywords from learning status
- **Output**: One-shot generation of all interaction suggestions (not conversational)

### 5.5 Structured Queries (`structured_query/`)

#### `__init__.py` - Core Query Functions

| Function | Purpose | Model |
|----------|---------|-------|
| `simple_query(prompt)` | Simple text completion | GPT-4o-2024-08-06 |
| `query_llm(prompt, history, format)` | Structured text output (Pydantic model) | GPT-4o-2024-08-06 |
| `query_vlm(prompt, history, image, format)` | Structured vision output (text + image) | GPT-4o-2024-08-06 |
| `process_chat_history(history)` | Converts chat history to text format | N/A |
| `encode_image(image_path)` | Base64-encodes images (or returns URL) | N/A |

All structured queries use `client.beta.chat.completions.parse()` with Pydantic `response_format` for type-safe outputs.

#### `step1.py` - Scene Description Queries

- **Pydantic Model**: `sceneDescriptionOutput` with `object_list: List[str]`
- **Purpose**: Decompose child's scene description into a list of 3D objects
- **Example**: "The big-eyed monkey is climbing the tree" → `["Monkey, big-eyed, action is climbing", "Tree"]`
- **Two modes**: Initial decomposition vs. refinement of existing list

#### `step2.py` - Spatial Selection Queries

- **Pydantic Model**: `spatialSelectionOutput` with `instruction: str` and `spatial_list: List[int]`
- **Purpose**: Analyze LEGO tutorial images and select 3 best spatial dimensions to teach
- **Uses Vision Model**: Sends tutorial image + chat history + learning progress
- **Output**: Detailed building instruction text + list of 3 spatial dimension indices (0-7)

### 5.6 Utilities (`utils/`)

#### `utils.py` - Core Utilities

| Function/Decorator | Purpose |
|-------------------|---------|
| `configure_user_session()` | Manages session IDs (random 6-digit or user input) |
| `configure_llm()` | LLM selection UI (gpt-4o-mini or custom key) |
| `enable_chat_history` | Decorator: renders chat history, initializes session state |
| `access_global_var` | Decorator: provides access to global `history_store_step_1` |
| `display_msg(msg, author)` | Adds message to session state and renders it |
| `welcome_message(page)` | Returns page-specific welcome message |
| `write_google_sheet(session_id)` | Logs conversations to Google Sheets |
| `choose_custom_openai_key()` | UI for entering custom OpenAI API key |
| `sync_st_session()` | Syncs session state |
| `stt_callback()` | Speech-to-text callback |

#### `step1.py` - Step 1 Utilities

| Function/Variable | Purpose |
|-------------------|---------|
| `history_store_step_1` | In-memory chat history store (dict) |
| `object_db` | Cache of generated LEGO model data |
| `get_history_step_1(session_id)` | Gets/creates chat history for session |
| `configure_objects()` | Sidebar UI for object display + model generation + voxelization |

#### `step2.py` - Step 2 Utilities

| Class/Function | Purpose |
|----------------|---------|
| `LearningStatus` | Tracks progress across 8 spatial dimensions, manages vocabulary advancement |
| `TutorialList` | Manages list of LEGO building tutorials |
| `Tutorial` | Single tutorial with step navigation |
| `configure_learning_status()` | Sidebar UI for progress bars + navigation buttons |
| `initialize_tutorial_list()` | Adds new tutorial instructions |
| `proceed_status(idx)` | Advances vocabulary to next word |

#### `step3.py` - Step 3 Utilities

| Function | Purpose |
|----------|---------|
| `get_history_step_3(session_id)` | Gets/creates chat history for Step 3 |

### 5.7 Streaming (`streaming.py`)

- **`StreamHandler`**: LangChain callback handler that writes tokens to a Streamlit container in real-time
- Inherits from `BaseCallbackHandler`
- Implements `on_llm_new_token()` to append tokens and update markdown display

---

## 6. Spatial Language Learning System

### 6.1 The 8 Spatial Dimensions

| Index | Dimension | Vocabulary Examples |
|-------|-----------|-------------------|
| 0 | Spatial Dimension | Big/Small, Long/Short, High/Low, Wide/Narrow, Thick/Thin, Deep/Shallow, Size, Length, Volume |
| 1 | Shape | Circle, Square, Rectangle, Triangle, Sphere, Cylinder, Cube, Cone, Polygon |
| 2 | Position and Direction | In, From/To, Up/Down, Front/Back, Left/Right, Inside/Outside, Middle/Side, Symmetry |
| 3 | Direction and Transformation | Forward/Backward, Left/Right, Up/Down, Flip, Rotate, Slide, Clockwise |
| 4 | Continuous Quantity | Whole/Part, All/Half/One Third, Majority/Minority, More/Less, Equal |
| 5 | Demonstratives | Here, There, Where, This, That, Which |
| 6 | Spatial Features and Attributes | Straight Line, Curve, Edge, Plane, Surface, Point, Acute/Obtuse/Right Angle |
| 7 | Patterns | Increase/Decrease, Before/After, Next/Previous, First/Last, Repeat, Order |

### 6.2 Learning Progression

Each vocabulary word goes through **3 stages**:
1. **Noun explanation** - Teaching the meaning
2. **Contextual application** - Using it during LEGO building
3. **Questioning and testing** - Testing comprehension

Progress is tracked per-dimension with percentage completion displayed as progress bars in the sidebar.

---

## 7. External API Integration

The app integrates with an external LEGO model generation service at `http://47.251.27.187`:

| Endpoint | Method | Input | Output |
|----------|--------|-------|--------|
| `/model/` | POST | `{"prompt": "object description"}` | `{"task_id": "...", "rendered_image_url": "..."}` |
| `/voxel/` | POST | `{"task_id": "model_task_id"}` | `{"task_id": "voxel_task_id"}` |
| `/lego_tutorial/` | POST | `{"task_id": "voxel_task_id"}` | `{"instructions": [...image_urls...]}` |

**Flow**: Text prompt → 3D model → Voxelized model → Step-by-step LEGO instructions (images)

---

## 8. UI Layout Summary

### 8.1 Homepage (`home.py`)
- **Main area**: Title "BrickSmart" with brick emoji, welcome message, "Click here to start!" button
- **Sidebar**: Navigation links (home, step1-3), Session ID input, Conversation info, LLM selection (radio buttons)

### 8.2 Step 1 - Scene Description
- **Main area**: Chat interface with assistant avatar, voice input button (Chinese), text input box
- **Sidebar**: Homepage link, divider, Block Info section showing extracted objects with generated LEGO preview images, "Start building" button

### 8.3 Step 2 - Block Building
- **Main area**: Chat interface showing tutorial images (top view + whole view) with AI-generated spatial language guidance
- **Sidebar**: Homepage/Step 1 links, "Next block"/"Start interacting" buttons, Current Progress section with 8 dimension progress bars, vocabulary display, "Learned" buttons

### 8.4 Step 3 - Block Interaction
- **Main area**: AI-generated interactive suggestions (vocabulary + dynamic instructions + parental guidance)
- **Sidebar**: Homepage/Step 1/Step 2 links

---

## 9. Session & State Management

- **Session ID**: Random 6-digit number or user-provided, used for chat history isolation
- **Chat histories**: Stored in module-level dictionaries (`history_store_step_1/2/3`) keyed by session ID
- **Streamlit session state** stores:
  - `current_page` - Active page name
  - `object_list` - Extracted 3D objects from scene description
  - `learning_status` - `LearningStatus` instance tracking spatial learning progress
  - `tutorial_list` - `TutorialList` instance managing building tutorials
  - Per-page message histories under `st.session_state[page_name]["messages"]`
- **Google Sheets** (optional): Conversations can be logged to Google Sheets worksheets named by session ID

---

## 10. OpenAI API Key Configuration

The app supports 3 methods for providing an OpenAI API key (checked in order):

1. **Local file**: `./openai.key` - text file containing the API key
2. **Streamlit secrets**: `.streamlit/secrets.toml` with `OPENAI_KEY = "sk-..."`
3. **Sidebar input**: User can select "use your openai api key" and enter it manually

---

## 11. Key Design Patterns

1. **Multi-page Streamlit app**: Uses `pages/` directory for automatic routing
2. **Decorator pattern**: `@enable_chat_history` and `@access_global_var` for cross-cutting concerns
3. **Class-per-page**: Each page has a chatbot class with `setup_chain()` and `main()` methods
4. **Structured outputs**: Pydantic models for type-safe LLM responses
5. **Dual LLM strategy**: GPT-4o for structured analysis, GPT-4o-mini for conversational chat
6. **Streaming responses**: Real-time token display via LangChain callbacks
7. **State machine**: Tutorial progression (TutorialList → Tutorial → Steps) and learning status tracking

---

## 12. Known Issues & Observations

1. **Dependency conflicts**: `fastembed` requires `numpy>=2.1.0` on Python 3.13, conflicting with `langchain`'s `numpy<2.0.0` requirement
2. **Version incompatibility**: `openai==1.41.0` with newer `httpx` versions causes `proxies` ValidationError in `ChatOpenAI`
3. **External API dependency**: The LEGO model generation relies on an external server (`47.251.27.187`) that may not always be available
4. **Hardcoded prompts**: All LLM prompts are embedded directly in the page files (not externalized)
5. **Chinese language**: Voice input is hardcoded to `zh-CN` (Chinese), suggesting the primary audience is Chinese-speaking families
6. **No authentication**: No user authentication or authorization system
7. **In-memory state**: Chat histories are stored in module-level dictionaries and will be lost on server restart
8. **Minimal error handling**: Some API calls have basic try/except but many edge cases are unhandled
9. **The `simple_query()` function** in `structured_query/__init__.py` has a hardcoded Chinese user message: "请告诉我怎么引导孩子用搭建好的乐高模型互动。" (Tell me how to guide children to interact with built LEGO models)

---

## 13. Run Instructions

```bash
# Install dependencies (Python 3.12 recommended; 3.13 has numpy conflicts)
pip install -r requirements.txt

# Set up OpenAI API key (choose one method):
# Method 1: Create key file
echo "sk-your-api-key" > openai.key

# Method 2: Create Streamlit secrets
mkdir .streamlit
echo 'OPENAI_KEY = "sk-your-api-key"' > .streamlit/secrets.toml

# Run the app
streamlit run home.py
# or
python -m streamlit run home.py

# Access at http://localhost:8501
```

---

*Analysis completed on February 12, 2026*
