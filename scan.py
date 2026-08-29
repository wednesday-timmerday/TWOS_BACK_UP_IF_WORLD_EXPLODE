# scan_deps.py
import ast
import os
import sys

EXCLUDE_DIRS = {".git", ".github", "build", "dist", "__pycache__", "venv", ".venv"}

# import name -> actual pip package name, when they differ
NAME_MAP = {
    "cv2": "opencv-python",
    "PIL": "pillow",
    "obsws_python": "obsws-python",
    "yaml": "pyyaml",
}

def find_py_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS]
        for f in filenames:
            if f.endswith(".py"):
                yield os.path.join(dirpath, f)

def local_module_names(root):
    names = set()
    for entry in os.listdir(root):
        full = os.path.join(root, entry)
        if entry in EXCLUDE_DIRS:
            continue
        if os.path.isdir(full):
            names.add(entry)
        elif entry.endswith(".py"):
            names.add(entry[:-3])
    return names

def extract_imports(path):
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        try:
            tree = ast.parse(f.read(), filename=path)
        except SyntaxError as e:
            print(f"SKIPPED (syntax error): {path} -> {e}")
            return set()

    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                found.add(node.module.split(".")[0])
    return found

def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    stdlib = set(sys.stdlib_module_names)
    local = local_module_names(root)

    all_imports = set()
    for path in find_py_files(root):
        all_imports |= extract_imports(path)

    third_party = sorted(all_imports - stdlib - local)
    packages = [NAME_MAP.get(name, name) for name in third_party]

    out_path = os.path.join(root, "requirements.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        for pkg in packages:
            f.write(pkg + "\n")

    print(f"Found {len(packages)} third-party packages -> {out_path}")
    for pkg in packages:
        print(" ", pkg)

if __name__ == "__main__":
    main()