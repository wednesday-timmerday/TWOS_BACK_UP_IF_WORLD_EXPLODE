import os
import json
import shutil
from groq import Groq  # Officiële Groq API-client

# -------------------------
# Configuration
# -------------------------
API_KEY = os.getenv("GROQ_API_KEY") or "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"
client = Groq(api_key=API_KEY)

PROJECT_DIR = "./"
BACKUP_DIR = "./backup_files"

# -------------------------
# Backup files
# -------------------------
def backup_file(file_path):
    backup_path = os.path.join(BACKUP_DIR, os.path.relpath(file_path, PROJECT_DIR))
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    shutil.copy2(file_path, backup_path)
    print(f"[Backup] {file_path} -> {backup_path}")

# -------------------------
# Load all project files
# -------------------------
def load_all_files(root_dir, extensions=None):
    context_data = {}
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            if extensions and not file.endswith(tuple(extensions)):
                continue
            file_path = os.path.join(subdir, file)
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    context_data[file_path] = f.read()
            except Exception as e:
                print(f"[Error] Reading {file_path}: {e}")
    return context_data

# -------------------------
# Split files into chunks
# -------------------------
def chunk_files(context_data, chunk_size=5):
    items = list(context_data.items())
    for i in range(0, len(items), chunk_size):
        yield dict(items[i:i + chunk_size])

# -------------------------
# Ask Groq a question
# -------------------------
def ask_groq(question, context_data):
    final_edits = {}
    for chunk in chunk_files(context_data, chunk_size=5):
        file_context = ""
        for fname, content in chunk.items():
            file_context += f"File: {fname}\n{content}\n\n"

        prompt = (
            "You are a helpful coding assistant.\n"
            "Decide which files need to be edited to answer the user's question.\n"
            "Return a JSON object with file paths as keys and new content as values.\n"
            "Do not modify files not needed.\n\n"
            f"Project files:\n{file_context}\n\n"
            f"Question: {question}\n"
            "Respond only with valid JSON."
        )

        try:
            response = client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[
                    {"role": "system", "content": "You are a code assistant."},
                    {"role": "user", "content": prompt},
                ],
            )
        except Exception as e:
            print("[Error] Groq request failed:", e)
            continue

        text = getattr(response.choices[0].message, "content", "")
        if not text:
            print("[Warning] Empty response for chunk")
            continue

        try:
            edits = json.loads(text)
            final_edits.update(edits)
        except Exception as e:
            print("[Error] Failed to parse JSON for chunk:", e)
            print("Raw response:", text)

    return final_edits

# -------------------------
# Show edits and ask approval
# -------------------------
def review_and_apply_edits(edits):
    for file_path, new_content in edits.items():
        print(f"\n--- Suggested edit for {file_path} ---")
        print(new_content[:500] + ("..." if len(new_content) > 500 else ""))
        approve = input("Apply this edit? (y/n): ").strip().lower()
        if approve == "y":
            if os.path.exists(file_path):
                backup_file(file_path)
            else:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
            print(f"[Applied] {file_path}")
        else:
            print(f"[Skipped] {file_path}")

# -------------------------
# Main interactive loop
# -------------------------
if __name__ == "__main__":
    print("=== Interactive Groq Project Assistant ===")
    # Alleen Python bestanden laden voor efficiency
    context_data = load_all_files(PROJECT_DIR, extensions=[".py"])
    print(f"Loaded {len(context_data)} .py files from project.")

    while True:
        question = input("\nEnter your question (or 'exit' to quit): ").strip()
        if question.lower() in ["exit", "quit"]:
            print("Goodbye!")
            break

        print("[Sending project files to Groq...]")
        edits = ask_groq(question, context_data)

        if edits:
            review_and_apply_edits(edits)
            context_data = load_all_files(PROJECT_DIR, extensions=[".py"])
        else:
            print("[No edits suggested by Groq.]")