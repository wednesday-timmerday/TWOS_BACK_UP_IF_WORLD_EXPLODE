import os
import re
from pathlib import Path
from openai import OpenAI
from tqdm import tqdm
import json

# --- CONFIGURATION ---
INPUT_DIR = "./my_pygame_project"
OUTPUT_DIR = "./my_c_sdl2_project"
TARGET_EXTENSIONS = [".py"]
API_KEY = os.getenv("DASHSCOPE_API_KEY")

client = OpenAI(
    api_key=API_KEY,
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
)
MODEL = "qwen-max" # Use qwen-max for complex architectural reasoning

MASTER_BLUEPRINT = {}

def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def clean_llm_output(text):
    """Removes markdown code blocks if the LLM wraps output in them."""
    text = re.sub(r'^```(?:c|h|cmake)?\n?', '', text.strip(), flags=re.MULTILINE)
    text = re.sub(r'\n?```$', '', text.strip(), flags=re.MULTILINE)
    return text.strip()

# ==========================================
# PASS 1: ARCHITECTURE BLUEPRINT GENERATION
# ==========================================
def pass1_build_blueprint():
    """Scans all files to map Python classes/modules to C structs/headers."""
    print("\n🔍 Pass 1: Analyzing Project Architecture...")
    
    all_files_summary = []
    for root, _, files in os.walk(INPUT_DIR):
        for file in files:
            if file.endswith(".py"):
                rel_path = os.path.relpath(os.path.join(root, file), INPUT_DIR)
                content = read_file(os.path.join(root, file))
                # Only send class defs and imports to save tokens
                summary = "\n".join([line for line in content.split('\n') if line.startswith(('class ', 'def ', 'import ', 'from '))])
                all_files_summary.append(f"File: {rel_path}\n{summary}")

    prompt = f"""
    You are an expert C software architect. I am converting a 50+ file Python/Pygame project to C using SDL2.
    Here is the structure of my Python project (classes, methods, imports):
    
    {'\n---\n'.join(all_files_summary)}
    
    Task: Create a JSON mapping blueprint. 
    1. Map every Python Class to a C Struct name.
    2. Map every Python file to a C Header (.h) and Source (.c) file name.
    3. Identify global game state (like screen, clock, event loop) that should go into a central 'game_state.h' struct.
    
    Output ONLY valid JSON in this format:
    {{
      "global_struct": "GameState",
      "files": {{
        "player.py": {{"c_file": "player.c", "h_file": "player.h", "structs": ["Player"]}},
        "main.py": {{"c_file": "main.c", "h_file": "main.h", "structs": []}}
      }}
    }}
    """
    
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1
    )
    
    global MASTER_BLUEPRINT
    try:
        MASTER_BLUEPRINT = json.loads(clean_llm_output(response.choices[0].message.content))
    except json.JSONDecodeError:
        print("❌ Failed to parse blueprint JSON. Retrying or check API output.")
        exit(1)
        
    with open(os.path.join(OUTPUT_DIR, "blueprint.json"), "w") as f:
        json.dump(MASTER_BLUEPRINT, f, indent=2)
    print("✅ Blueprint generated.")

# ==========================================
# PASS 2 & 3: TRANSLATE FILES TO .h AND .c
# ==========================================
def translate_file(py_filepath, rel_path):
    """Translates a single Python file into a .h and .c file using the blueprint."""
    py_code = read_file(py_filepath)
    
    # Determine output filenames from blueprint
    file_map = MASTER_BLUEPRINT.get("files", {}).get(rel_path, {})
    c_filename = file_map.get("c_file", Path(rel_path).with_suffix(".c").name)
    h_filename = file_map.get("h_file", Path(rel_path).with_suffix(".h").name)
    structs = file_map.get("structs", [])
    global_struct = MASTER_BLUEPRINT.get("global_struct", "GameState")

    system_prompt = f"""
    You are an expert C developer translating Python/Pygame to C/SDL2.
    
    CRITICAL RULES FOR C TRANSLATION:
    1. PYGAME REPLACEMENTS:
       - pygame.init() -> SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO)
       - pygame.display.set_mode() -> SDL_CreateWindow() + SDL_CreateRenderer()
       - pygame.image.load() -> IMG_Load() (from SDL2_image)
       - pygame.mixer -> Mix_Music / Mix_Chunk (from SDL2_mixer)
       - pygame.event.get() -> SDL_PollEvent()
       - pygame.Rect -> SDL_Rect
       - Surface blitting -> SDL_RenderCopy()
    2. OOP TO C:
       - Python `self` becomes the first argument of a function: `void player_update(Player* self, GameState* gs)`
       - Python classes become C structs. Methods become standalone functions taking the struct pointer.
       - __init__ becomes a `_create()` or `_init()` function.
       - __del__ or cleanup becomes a `_destroy()` or `_free()` function.
    3. MEMORY: Use malloc/calloc for creation, free for destruction. No memory leaks.
    4. INCLUDES: Always include SDL2 headers where necessary. Include "{h_filename}" in the C file.
    5. GLOBAL STATE: Pass `{global_struct}* gs` to functions that need access to the renderer, window, or other systems.
    
    Target Structs for this file: {', '.join(structs) if structs else 'None (Utility functions only)'}
    """

    user_prompt = f"""
    Translate the following Python/Pygame file into two separate outputs: a Header file (.h) and a Source file (.c).
    
    Original File: {rel_path}
    ```python
    {py_code}
    ```
    
    FORMAT YOUR RESPONSE EXACTLY LIKE THIS:
    ===HEADER===
    (your .h code here)
    ===SOURCE===
    (your .c code here)
    """

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2
    )

    raw_output = response.choices[0].message.content
    
    # Split the response into .h and .c
    if "===HEADER===" in raw_output and "===SOURCE===" in raw_output:
        parts = raw_output.split("===SOURCE===")
        h_code = clean_llm_output(parts[0].replace("===HEADER===", ""))
        c_code = clean_llm_output(parts[1])
    else:
        # Fallback if LLM ignores formatting
        h_code = f"#ifndef {h_filename.upper().replace('.', '_')}\n#define {h_filename.upper().replace('.', '_')}\n// Warning: LLM failed to split\n#endif"
        c_code = clean_llm_output(raw_output)

    # Save files
    out_dir = os.path.join(OUTPUT_DIR, os.path.dirname(rel_path))
    os.makedirs(out_dir, exist_ok=True)
    
    with open(os.path.join(out_dir, h_filename), "w", encoding="utf-8") as f:
        f.write(h_code)
    with open(os.path.join(out_dir, c_filename), "w", encoding="utf-8") as f:
        f.write(c_code)


# ==========================================
# PASS 4: GENERATE CMAKE BUILD SYSTEM
# ==========================================
def generate_cmake():
    """Generates a CMakeLists.txt to easily compile the 50+ files."""
    print("\n⚙️ Generating CMakeLists.txt...")
    
    cmake_content = """cmake_minimum_required(VERSION 3.10)
project(PygameToSDL2 C)

set(CMAKE_C_STANDARD 11)

# Find SDL2 packages
find_package(SDL2 REQUIRED)
find_package(SDL2_image REQUIRED)
find_package(SDL2_mixer REQUIRED)
find_package(SDL2_ttf REQUIRED)

include_directories(${SDL2_INCLUDE_DIRS} ${CMAKE_SOURCE_DIR})

# Automatically gather all .c files
file(GLOB_RECURSE SOURCES "src/*.c")

add_executable(game ${SOURCES})

target_link_libraries(game 
    ${SDL2_LIBRARIES} 
    SDL2_image::SDL2_image 
    SDL2_mixer::SDL2_mixer 
    SDL2_ttf::SDL2_ttf
    m # Math library
)
"""
    with open(os.path.join(OUTPUT_DIR, "CMakeLists.txt"), "w") as f:
        f.write(cmake_content)


# ==========================================
# MAIN EXECUTION LOOP
# ==========================================
def main():
    if not API_KEY:
        print("❌ Set DASHSCOPE_API_KEY environment variable!")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1. Build Blueprint
    pass1_build_blueprint()

    # 2. Gather all python files
    py_files = []
    for root, _, files in os.walk(INPUT_DIR):
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, INPUT_DIR)
                py_files.append((full_path, rel_path))

    # 3. Translate each file
    print(f"\n🔄 Pass 2 & 3: Translating {len(py_files)} files to C/SDL2...")
    for full_path, rel_path in tqdm(py_files):
        try:
            translate_file(full_path, rel_path)
        except Exception as e:
            print(f"\n❌ Error translating {rel_path}: {e}")

    # 4. Generate Build System
    generate_cmake()
    
    print("\n✅ CONVERSION COMPLETE!")
    print(f"Output directory: {OUTPUT_DIR}")
    print("Next steps:")
    print("1. Install SDL2, SDL2_image, SDL2_mixer, SDL2_ttf on your system.")
    print("2. Move all generated .c and .h files into a 'src/' folder inside the output dir.")
    print("3. Run: mkdir build && cd build && cmake .. && make")

if __name__ == "__main__":
    main()