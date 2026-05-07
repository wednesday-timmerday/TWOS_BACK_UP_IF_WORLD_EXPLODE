import random
import sympy as sp

x = sp.Symbol('x')

# allowed operations
ops = ['+', '-', '*']

def random_expr(depth=0):
    """Build a random symbolic expression."""
    if depth > 3:
        return random.randint(1, 10)

    choice = random.choice(['num', 'op'])

    if choice == 'num':
        return random.randint(1, 10)

    # recursive expression
    left = random_expr(depth + 1)
    right = random_expr(depth + 1)
    op = random.choice(ops)

    return f"({left} {op} {right})"


def generate_equation(target):
    """Try to generate an expression that evaluates to target."""
    for _ in range(10000):  # brute force attempts
        expr_str = random_expr()
        try:
            value = eval(expr_str)
            if value == target:
                return expr_str
        except ZeroDivisionError:
            continue

    return "NO MATCH FOUND... ERROR STATIC NOISE"

# example
target_number = 42
result = generate_equation(target_number)

print("TARGET:", target_number)
print("EQUATION:", result)