#!/usr/bin/env python3
"""T11 static metrics: exact function length / nesting depth / swallowed excepts / bare excepts / mutable default args (Python AST)."""
import ast, sys

NEST = (ast.If, ast.For, ast.While, ast.With, ast.Try)

def analyze(path):
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)
    funcs = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs.append((node.name, node.lineno, node.end_lineno - node.lineno + 1))
    maxdepth, maxline = 0, 0
    def depth(node, d):
        nonlocal maxdepth, maxline
        for child in ast.iter_child_nodes(node):
            nd = d + 1 if isinstance(child, NEST) else d
            if nd > maxdepth:
                maxdepth, maxline = nd, getattr(child, "lineno", 0)
            depth(child, nd)
    depth(tree, 0)
    swallowed, bare = [], []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                bare.append(node.lineno)
            if len(node.body) == 1 and isinstance(node.body[0], (ast.Pass, ast.Continue)):
                swallowed.append(node.lineno)
    mutdef = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in list(node.args.defaults) + [x for x in node.args.kw_defaults if x]:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    mutdef.append((node.name, node.lineno))
    return funcs, maxdepth, maxline, swallowed, bare, mutdef

for path in sys.argv[1:]:
    try:
        funcs, md, ml, sw, bare, mut = analyze(path)
    except Exception as e:
        print(f"== {path} PARSE_ERROR {e}"); continue
    over = sorted([f for f in funcs if f[2] > 50], key=lambda x: -x[2])
    print(f"== {path} funcs={len(funcs)} over50={len(over)} max_nest={md}@L{ml} swallowed_except={sw} bare_except={bare} mutable_default={mut}")
    for name, line, ln in over:
        print(f"   OVER50 {name} L{line} len={ln}")
