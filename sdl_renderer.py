# Create mappings.txt

with open("mappings.txt", "w") as f:
    # Lowercase letters
    for c in "abcdefghijklmnopqrstuvwxyz":
        f.write(f"{c}={c}\n")

    # Numbers
    for n in "0123456789":
        f.write(f"{n}={n}\n")

    # Special keys
    f.write("ctrl=ctrl\n")
    f.write("shift=shift\n")

print("mappings.txt created.")