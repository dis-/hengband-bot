#!/usr/bin/env python3
"""Move selected class methods into a mixin without rewriting their bodies."""

from __future__ import annotations

import argparse
import ast
import builtins
import fnmatch
from dataclasses import dataclass
from pathlib import Path
import re
import symtable
import sys
from typing import Iterable


class SplitMoveError(RuntimeError):
    """A requested move is unsafe or internally inconsistent."""


@dataclass(frozen=True)
class MethodSpan:
    name: str
    node: ast.FunctionDef | ast.AsyncFunctionDef
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class MovePlan:
    methods: tuple[MethodSpan, ...]
    import_lines: tuple[str, ...]
    constants_to_relocate: tuple[str, ...]
    decorated_methods: tuple[str, ...]
    decorator_sentinels: tuple[str, ...]
    original_decorators: tuple[tuple[str, tuple[str, ...]], ...]
    source_delta: int
    target_delta: int


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    raise SplitMoveError(f"source class {name!r} was not found")


def _attached_start(lines: list[str], node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    start = min([node.lineno, *(item.lineno for item in node.decorator_list)]) - 1
    indent = re.match(r"\s*", lines[start]).group(0)
    while start and re.match(rf"^{re.escape(indent)}#", lines[start - 1]):
        start -= 1
    return start


def _spans(text: str, class_name: str) -> tuple[MethodSpan, ...]:
    lines = text.splitlines(keepends=True)
    cls = _class(ast.parse(text), class_name)
    answer = []
    for node in cls.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        start = _attached_start(lines, node)
        end = node.end_lineno or node.lineno
        answer.append(MethodSpan(node.name, node, start, end, "".join(lines[start:end])))
    return tuple(answer)


def _matches(name: str, selector: str) -> bool:
    return fnmatch.fnmatchcase(name, selector) if any(char in selector for char in "*?[") else name == selector


def select_methods(spans: Iterable[MethodSpan], selectors: Iterable[str]) -> tuple[MethodSpan, ...]:
    spans = tuple(spans)
    selectors = tuple(selectors)
    missing = [selector for selector in selectors if not any(_matches(span.name, selector) for span in spans)]
    if missing:
        raise SplitMoveError("selector(s) matched nothing: " + ", ".join(missing))
    return tuple(span for span in spans if any(_matches(span.name, selector) for selector in selectors))


def _module_bindings(tree: ast.Module) -> tuple[dict[str, ast.stmt], set[str]]:
    bindings: dict[str, ast.stmt] = {}
    constants: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                bindings[alias.asname or alias.name.split(".")[0]] = node
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                bindings[alias.asname or alias.name] = node
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bindings[node.name] = node
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name):
                    bindings[target.id] = node
                    if target.id.isupper():
                        constants.add(target.id)
    return bindings, constants


def _free_names(methods: Iterable[MethodSpan]) -> set[str]:
    result: set[str] = set()
    builtin_names = set(dir(builtins))
    for span in methods:
        table = symtable.symtable(ast.unparse(span.node), "<moved method>", "exec")

        def collect(scope: symtable.SymbolTable) -> None:
            for symbol in scope.get_symbols():
                if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in builtin_names:
                    result.add(symbol.get_name())
            for child in scope.get_children():
                collect(child)

        collect(table)
    return result


def _render_import(node: ast.Import | ast.ImportFrom, wanted: set[str]) -> str:
    aliases = [alias for alias in node.names if (alias.asname or alias.name.split(".")[0]) in wanted]
    if isinstance(node, ast.Import):
        return "import " + ", ".join(alias.name + (f" as {alias.asname}" if alias.asname else "") for alias in aliases)
    dots = "." * node.level
    module = node.module or ""
    names = ", ".join(alias.name + (f" as {alias.asname}" if alias.asname else "") for alias in aliases)
    return f"from {dots}{module} import {names}"


def build_plan(source_text: str, source_class: str, selectors: Iterable[str]) -> MovePlan:
    tree = ast.parse(source_text)
    methods = select_methods(_spans(source_text, source_class), selectors)
    bindings, local_constants = _module_bindings(tree)
    free = _free_names(methods)
    unresolved = sorted(free - bindings.keys())
    if unresolved:
        raise SplitMoveError("unresolved free names in moved methods: " + ", ".join(unresolved))
    constants = tuple(sorted(free & local_constants))
    wanted_imports = free - set(constants)
    import_nodes: list[ast.Import | ast.ImportFrom] = []
    source_local = []
    for name in sorted(wanted_imports):
        binding = bindings[name]
        if isinstance(binding, (ast.Import, ast.ImportFrom)):
            if binding not in import_nodes:
                import_nodes.append(binding)
        else:
            source_local.append(name)
    imports = [_render_import(node, wanted_imports) for node in import_nodes]
    if source_local:
        imports.append("from .policy import " + ", ".join(source_local))
    if constants:
        imports.append("from .policy_constants import " + ", ".join(constants))
    source_lines = source_text.splitlines()
    removed = sum(span.end - span.start for span in methods)
    decorated = tuple(span.name for span in methods if span.node.decorator_list)
    all_spans = _spans(source_text, source_class)
    moved_names = {span.name for span in methods}
    sentinels = tuple(all_spans[index + 1].name for index, span in enumerate(all_spans[:-1])
                      if span.name in moved_names and span.node.decorator_list
                      and all_spans[index + 1].name not in moved_names)
    original_decorators = tuple(
        (span.name, tuple(ast.dump(item, include_attributes=False) for item in span.node.decorator_list))
        for span in all_spans
    )
    target_lines = 4 + sum(span.text.count("\n") for span in methods)
    return MovePlan(methods, tuple(imports), constants, decorated, sentinels,
                    original_decorators, -removed + 1, target_lines)


def _normalized(node: ast.AST) -> str:
    node = ast.fix_missing_locations(node)
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and ast.get_docstring(node, clean=False) is not None:
        copy = ast.parse(ast.unparse(node)).body[0]
        if isinstance(copy.body[0], ast.Expr) and isinstance(copy.body[0].value, ast.Constant):
            copy.body[0].value.value = "<docstring>"
        node = copy
    return ast.dump(node, include_attributes=False)


def verify_move(original: MovePlan, source_text: str, target_text: str, source_class: str, mixin_name: str) -> None:
    source_tree = ast.parse(source_text)
    target_tree = ast.parse(target_text)
    remaining = {node.name for node in _class(source_tree, source_class).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    leftovers = sorted(span.name for span in original.methods if span.name in remaining)
    if leftovers:
        raise SplitMoveError("moved names remain in source class: " + ", ".join(leftovers))
    expected_decorators = dict(original.original_decorators)
    for node in _class(source_tree, source_class).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            actual = tuple(ast.dump(item, include_attributes=False) for item in node.decorator_list)
            if actual != expected_decorators[node.name]:
                raise SplitMoveError(f"decorator was stranded onto {node.name}")
    target_methods = {node.name: node for node in _class(target_tree, mixin_name).body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for span in original.methods:
        moved = target_methods.get(span.name)
        if moved is None or _normalized(span.node) != _normalized(moved):
            raise SplitMoveError(f"AST identity failed for {span.name}")
        if bool(span.node.decorator_list) != bool(moved.decorator_list):
            raise SplitMoveError(f"decorator was stranded for {span.name}")
    target_bindings, _ = _module_bindings(target_tree)
    unresolved = sorted(_free_names(MethodSpan(n.name, n, 0, 0, "") for n in target_methods.values()) - target_bindings.keys())
    if unresolved:
        raise SplitMoveError("new module has unresolved free names: " + ", ".join(unresolved))
    compile(target_text, "<split target>", "exec")


def render(source_text: str, plan: MovePlan, source_class: str, target_module: str, mixin_name: str) -> tuple[str, str]:
    if plan.constants_to_relocate:
        raise SplitMoveError("constants must be relocated to policy_constants before applying: " + ", ".join(plan.constants_to_relocate))
    lines = source_text.splitlines(keepends=True)
    for span in reversed(plan.methods):
        del lines[span.start:span.end]
    changed = "".join(lines)
    import_line = f"from .{target_module} import {mixin_name}\n"
    insert_at = max((node.end_lineno or node.lineno for node in ast.parse(changed).body if isinstance(node, (ast.Import, ast.ImportFrom))), default=0)
    changed_lines = changed.splitlines(keepends=True)
    changed_lines.insert(insert_at, import_line)
    changed = "".join(changed_lines)
    cls = _class(ast.parse(changed), source_class)
    header_end = changed.find(":", changed_lines and sum(len(x) for x in changed_lines[:cls.lineno - 1]))
    header = changed[:header_end]
    if "(" in header[header.rfind("class "):]:
        changed = changed[:header_end] + f", {mixin_name}" + changed[header_end:]
    else:
        changed = changed[:header_end] + f"({mixin_name})" + changed[header_end:]
    body = "\n\n".join(span.text.rstrip() for span in plan.methods)
    target = "\n".join((*plan.import_lines, "", f"class {mixin_name}:", body, ""))
    verify_move(plan, changed, target, source_class, mixin_name)
    return changed, target


def _print_plan(plan: MovePlan) -> None:
    print(f"Matched methods ({len(plan.methods)}): " + ", ".join(span.name for span in plan.methods))
    print("Imports to add:")
    for line in plan.import_lines:
        print(f"  {line}")
    print("Constants needing relocation: " + (", ".join(plan.constants_to_relocate) or "none"))
    print("Decorated methods: " + (", ".join(plan.decorated_methods) or "none"))
    print("Decorator-stranding sentinels: " + (", ".join(plan.decorator_sentinels) or "none"))
    print(f"Expected line deltas: source {plan.source_delta:+d}, target {plan.target_delta:+d}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("mixin")
    parser.add_argument("selectors", nargs="+")
    parser.add_argument("--source-class", default="HengbotPolicy")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--constants-plan", action="store_true")
    args = parser.parse_args(argv)
    try:
        source_text = args.source.read_text(encoding="utf-8")
        plan = build_plan(source_text, args.source_class, args.selectors)
        _print_plan(plan)
        if args.dry_run or args.constants_plan:
            return 0
        changed, target = render(source_text, plan, args.source_class, args.target.stem, args.mixin)
        if args.target.exists():
            raise SplitMoveError(f"target already exists: {args.target}")
        args.source.write_text(changed, encoding="utf-8", newline="")
        args.target.write_text(target, encoding="utf-8", newline="")
        return 0
    except (OSError, SyntaxError, SplitMoveError) as error:
        print(f"split_move: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
