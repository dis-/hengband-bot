"""Mechanical review of town-work census sites that provably cannot emit work.

A census site needs no hand review entry, and is recorded as observational
data, only when the AST proves all of the following. Anything unproved keeps
needing a hand review, so the proof can only remove entries that never decide
anything at run time:

* its only origin is the producer census (no @claims, ladder, registry,
  decision, design-table or emit/driver tag);
* it emits no key: no return, yield or lambda body can be a non-empty str (the
  town_work observer records only non-empty str returns). Proved are non-str
  and empty str constants, comparisons, `not`/unary operators, containers,
  numeric and bitwise operators, `and` chains whose last operand is proved (an
  earlier operand is returned only when falsy, and a falsy str is empty), the
  safe builtins below, max/min/next over proved operands or comprehension
  elements, max/min of several operands one of which is a number constant (a
  str operand would raise on comparison), local names whose every write is proved, module constants whose
  every module-level write is proved, instances of a source class that cannot
  be a str (no __new__ or metaclass, every base a known non-str type or such a
  class), and calls of a module function (by name, or through an imported
  hengbot module) or a self/cls method whose every same-named definition is
  proved (builtin operator semantics assumed);
* it calls no send seam, directly or through any same-named callee or the
  __init__/__post_init__ of a constructed source class;
* it mutates no object it did not create: no assignment, deletion or
  mutating method call rooted at anything but a fresh local container, no
  setattr/global/nonlocal, and every module function, self/cls method and
  constructed source class's __init__/__post_init__ (which may set attributes
  of the new object) it calls is proved the same way;
* it does not call a parameter, a subscript or a call result (a callback may
  be a producer), and has no decorator other than the read-only ones.

Module-level resolution (imported modules, constants and classes) needs the
sources; without them only the function bodies are read and fewer sites are
proved.

The proof reads neither line numbers nor AST digests: an edit that keeps these
properties needs no review and changes no generated file.
"""
from __future__ import annotations

import ast

import town_structure_lint as lint

# The runtime index row of a proved site (town_work.py reads these fields).
DATA_REVIEW = {'classification': 'data', 'rows': ['data/no-independent-credit'],
               'delegation': 'selected child; no independent success'}
SAFE_BUILTINS = frozenset({
    'bool', 'int', 'float', 'len', 'any', 'all', 'isinstance', 'issubclass', 'hasattr', 'callable',
    'sum', 'abs', 'round', 'frozenset', 'set', 'list', 'tuple', 'dict', 'sorted', 'range',
    'enumerate', 'zip', 'reversed', 'divmod', 'id', 'hash', 'ord'})
# Builtins returning one of their operands, an element of their one comprehension operand or the default.
SELECTING_BUILTINS = frozenset({'max', 'min', 'next'})
COMPREHENSIONS = (ast.GeneratorExp, ast.ListComp, ast.SetComp)
MUTATORS = frozenset({
    'append', 'extend', 'add', 'update', 'setdefault', 'pop', 'popitem', 'remove', 'discard',
    'clear', 'insert', 'sort', 'reverse', 'appendleft', 'popleft', 'extendleft', 'rotate',
    'write', 'put', 'difference_update', 'intersection_update', 'symmetric_difference_update'})
DYNAMIC = frozenset({'setattr', 'delattr', 'exec', 'eval', 'globals', '__setattr__', '__delattr__'})
FRESH_CONSTRUCTORS = frozenset({'dict', 'list', 'set', 'defaultdict', 'Counter', 'OrderedDict', 'deque'})
FRESH_DISPLAYS = (ast.List, ast.Tuple, ast.Set, ast.Dict, ast.ListComp, ast.SetComp, ast.DictComp)
READ_ONLY_DECORATORS = frozenset({'property', 'staticmethod', 'classmethod', 'cached_property',
                                  'lru_cache', 'cache'})
NON_STR_NODES = (ast.Compare, ast.UnaryOp, ast.GeneratorExp, ast.Lambda) + FRESH_DISPLAYS
# Operators that never produce a str whatever their (builtin) operands are.
NON_STR_OPERATORS = (ast.Sub, ast.Div, ast.FloorDiv, ast.Pow, ast.BitAnd, ast.BitXor, ast.BitOr,
                     ast.LShift, ast.RShift, ast.MatMult)
SEAM_PREFIXES = ('_send_', '_consume_response_')
# Bases (not defined in the sources) whose subclasses' instances are not str. str and StrEnum are absent.
NON_STR_BASES = frozenset({
    'object', 'NamedTuple', 'TypedDict', 'Enum', 'IntEnum', 'Flag', 'IntFlag', 'Protocol', 'ABC',
    'Generic', 'Exception', 'ValueError', 'RuntimeError', 'KeyError', 'LookupError', 'TypeError',
    'OSError', 'int', 'float', 'tuple', 'list', 'dict', 'set', 'frozenset'})
# Class decorators that return the class they decorate.
CLASS_DECORATORS = frozenset({'dataclass', 'total_ordering', 'unique', 'final', 'runtime_checkable'})
# The methods a constructor call runs on the new object (which they may mutate).
CONSTRUCTION = ('__init__', '__post_init__')
MAX_DEPTH = 16


def _root(node):
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Starred)):
        node = node.value
    return node.id if isinstance(node, ast.Name) else None


def _leaves(target):
    if isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            yield from _leaves(element)
    elif isinstance(target, ast.Starred):
        yield from _leaves(target.value)
    else:
        yield target


def _targets(node):
    if isinstance(node, (ast.Assign, ast.Delete)):
        return node.targets
    if isinstance(node, (ast.AugAssign, ast.AnnAssign, ast.NamedExpr, ast.For, ast.AsyncFor,
                         ast.comprehension)):
        return [node.target]
    if isinstance(node, ast.withitem) and node.optional_vars is not None:
        return [node.optional_vars]
    return []


def _fresh(value):
    return isinstance(value, FRESH_DISPLAYS) or (
        isinstance(value, ast.Call) and lint.name(value.func) in FRESH_CONSTRUCTORS)


def _module_name(filename):
    parts = filename.removesuffix('.py').split('/')
    return '.'.join(parts[:-1] if parts[-1] == '__init__' else parts)


def _base(node):
    """A class base without its subscript (Generic[T] -> Generic)."""
    return node.value if isinstance(node, ast.Subscript) else node


class _Modules:
    """The module-level bindings of the sources, to resolve a name a function does not bind itself.

    A binding is ('function', site), ('class', filename, ClassDef), ('module', filename),
    ('member', filename, name) (an import of a module member) or ('value', filename, expression).
    None is anything else (a non-hengbot import, an unpacked, augmented or loop write, a `global`
    write in a function, a deletion); a name with one such binding resolves to nothing.
    """

    def __init__(self, sources):
        self.files = {_module_name(filename): filename for filename in sources}
        self.bindings = {filename: self._bind(filename, ast.parse(source))
                         for filename, source in sources.items()}

    def imported(self, filename, node):
        """(name, binding) for each name an import statement in filename binds."""
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.removeprefix('hengbot.')
                if alias.asname:
                    yield alias.asname, (('module', self.files[module])
                                         if alias.name.startswith('hengbot.') and module in self.files
                                         else None)
                else:
                    yield alias.name.split('.')[0], None
            return
        if node.level:
            package = _module_name(filename).split('.') if _module_name(filename) else []
            if not filename.endswith('__init__.py'):
                package = package[:-1]
            package = package[:len(package) - node.level + 1]
            module = '.'.join(package + ([node.module] if node.module else []))
        elif node.module == 'hengbot' or (node.module or '').startswith('hengbot.'):
            module = node.module.removeprefix('hengbot').removeprefix('.')
        else:
            module = None
        for alias in node.names:
            bound = alias.asname or alias.name
            child = f'{module}.{alias.name}' if module else alias.name
            if module is None or alias.name == '*':
                yield bound, None
            elif child in self.files:
                yield bound, ('module', self.files[child])
            elif module in self.files:
                yield bound, ('member', self.files[module], alias.name)
            else:
                yield bound, None

    def _bind(self, filename, tree):
        bindings = {}

        def bind(name, binding):
            bindings.setdefault(name, []).append(binding)

        def walk(statements):
            for node in statements:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    bind(node.name, ('function', f'{filename}:{node.name}'))
                elif isinstance(node, ast.ClassDef):
                    bind(node.name, ('class', filename, node))
                elif isinstance(node, (ast.Import, ast.ImportFrom)):
                    for name, binding in self.imported(filename, node):
                        bind(name, binding)
                else:
                    for target in _targets(node):
                        for leaf in _leaves(target):
                            if isinstance(leaf, ast.Name) and not (
                                    isinstance(node, ast.AnnAssign) and node.value is None):
                                exact = isinstance(node, (ast.Assign, ast.AnnAssign)) and leaf is target
                                bind(leaf.id, ('value', filename, node.value) if exact else None)
                    for item in getattr(node, 'items', ()):
                        for leaf in _leaves(item.optional_vars) if item.optional_vars else ():
                            if isinstance(leaf, ast.Name):
                                bind(leaf.id, None)
                    # A walrus binds in the module scope wherever it is (outside a function).
                    for inner in ast.walk(node):
                        if isinstance(inner, ast.NamedExpr):
                            bind(inner.target.id, None)
                    for handler in getattr(node, 'handlers', ()):
                        if handler.name:
                            bind(handler.name, None)
                        walk(handler.body)
                    for field in ('body', 'orelse', 'finalbody'):
                        walk(getattr(node, field, []))
        walk(tree.body)
        # A function may rebind a module name with `global`; anything written so is unknown.
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                for name in node.names:
                    bind(name, None)
        return bindings

    def resolve(self, filename, name, depth=0):
        """Every definition a module-level name of filename may denote, or None when one is unknown."""
        bindings = self.bindings.get(filename, {}).get(name)
        if not bindings or depth > MAX_DEPTH:
            return None
        found = []
        for binding in bindings:
            if binding is None:
                return None
            if binding[0] == 'member':
                inner = self.resolve(binding[1], binding[2], depth + 1)
                if inner is None:
                    return None
                found.extend(inner)
            else:
                found.append(binding)
        return found

    def base_classes(self, filename, base):
        """The source classes a class base names, [] for a non-source name, None when unknown."""
        base = _base(base)
        if isinstance(base, ast.Name):
            found = self.resolve(filename, base.id)
            if found is None:
                return [] if base.id in NON_STR_BASES else None
        elif isinstance(base, ast.Attribute) and isinstance(base.value, ast.Name):
            module = self.resolve(filename, base.value.id)
            if module is None:
                return [] if base.attr in NON_STR_BASES else None
            if len(module) != 1 or module[0][0] != 'module':
                return None
            found = self.resolve(module[0][1], base.attr)
        else:
            return None
        if not found or any(binding[0] != 'class' for binding in found):
            return None
        return found

    def non_str_class(self, filename, node, depth=0):
        """Whether calling this source class can only return an instance that is not a str."""
        if depth > MAX_DEPTH or node.keywords or any(
                isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == '__new__'
                for n in node.body):
            return False
        if any(lint.name(d.func if isinstance(d, ast.Call) else d) not in CLASS_DECORATORS
               for d in node.decorator_list):
            return False
        for base in node.bases:
            found = self.base_classes(filename, base)
            if found is None or not all(self.non_str_class(b[1], b[2], depth + 1) for b in found):
                return False
        return True

    def construction_sites(self, filename, node, functions, depth=0):
        """The __init__/__post_init__ sites a call of this class (or of its source bases) may run."""
        found = {f'{filename}:{node.name}.{method}' for method in CONSTRUCTION} & functions.keys()
        if depth < MAX_DEPTH:
            for base in node.bases:
                for binding in self.base_classes(filename, base) or ():
                    found |= self.construction_sites(binding[1], binding[2], functions, depth + 1)
        return found


class _Site:
    """What one function body shows; the fixpoints combine these per callee."""

    def __init__(self, function, filename=None, modules=None, nested=False):
        arguments = function.args
        self.filename, self.modules = filename, modules
        # A free name of a nested function may be a local of the enclosing one: never resolved.
        self.nested = nested
        self.params = {a.arg for a in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
                                       arguments.vararg, arguments.kwarg) if a}
        nodes = list(lint.local_nodes(function))
        # Every value a local name is bound to; None marks an unpacked or loop binding.
        self.writes = {}
        for node in nodes:
            for target in _targets(node):
                exact = isinstance(target, ast.Name) and isinstance(node, (ast.Assign, ast.AnnAssign,
                                                                           ast.NamedExpr))
                for leaf in _leaves(target):
                    if isinstance(leaf, ast.Name):
                        self.writes.setdefault(leaf.id, []).append(node.value if exact else None)
        self.fresh = {name for name, values in self.writes.items()
                      if name not in self.params and all(_fresh(v) for v in values)}
        # The object a constructor initialises is the one its call creates.
        if function.name in CONSTRUCTION and arguments.args:
            self.fresh.add(arguments.args[0].arg)
        # Names a local import binds (they are not in writes); None is a non-hengbot import.
        self.imports = {}
        for node in nodes:
            if modules is not None and isinstance(node, (ast.Import, ast.ImportFrom)):
                for name, binding in modules.imported(filename, node):
                    self.imports.setdefault(name, []).append(binding)
        self.values = [n.value for n in nodes if isinstance(n, (ast.Return, ast.Yield))]
        # A lambda's code is attributed to this site by town_work.code_site.
        self.values += [n.body for n in nodes if isinstance(n, ast.Lambda)]
        self.problems = []
        self.called = set()
        self.calls = []
        for node in nodes:
            self._inspect(node)
        for decorator in function.decorator_list:
            if lint.name(decorator.func if isinstance(decorator, ast.Call) else decorator) \
                    not in READ_ONLY_DECORATORS:
                self.problems.append('decorator')

    @classmethod
    def module_scope(cls, filename, modules):
        """A frame for a module-level expression: no parameters, locals or local imports."""
        site = cls.__new__(cls)
        site.filename, site.modules, site.nested = filename, modules, False
        site.params, site.writes, site.fresh, site.imports = set(), {}, set(), {}
        return site

    def _foreign(self, node):
        """Whether node may be rooted at an object this function did not create."""
        return _root(node) not in self.fresh

    def _inspect(self, node):
        if isinstance(node, (ast.Global, ast.Nonlocal, ast.Await, ast.YieldFrom, ast.Delete)):
            self.problems.append(type(node).__name__)
        for target in _targets(node):
            for leaf in _leaves(target):
                if isinstance(leaf, (ast.Attribute, ast.Subscript)) and self._foreign(leaf):
                    self.problems.append('mutation')
        if not isinstance(node, ast.Call):
            return
        name = lint.name(node.func)
        if name in DYNAMIC:
            self.problems.append('dynamic')
        if not isinstance(node.func, (ast.Name, ast.Attribute)) or (
                isinstance(node.func, ast.Name) and name in self.params | self.writes.keys()):
            self.problems.append('indirect call')
            return
        self.called.add(name)
        self.calls.append(node.func)
        if isinstance(node.func, ast.Attribute) and name in MUTATORS and self._foreign(node.func.value):
            self.problems.append('mutation')

    def _local(self, name):
        return name in self.writes or name in self.params

    def resolve(self, name):
        """The module-level definitions a name this function does not bind may denote, or None."""
        if self.modules is None or self.nested or self._local(name):
            return None
        if name not in self.imports:
            return self.modules.resolve(self.filename, name)
        found = []
        for binding in self.imports[name]:
            inner = None if binding is None else (
                self.modules.resolve(binding[1], binding[2]) if binding[0] == 'member' else [binding])
            if inner is None:
                return None
            found.extend(inner)
        return found

    def _attribute(self, node):
        """The definitions `module.name` denotes when module is an imported source module, or None."""
        if not isinstance(node, ast.Attribute) or not isinstance(node.value, ast.Name):
            return None
        module = self.resolve(node.value.id)
        if not module or len(module) != 1 or module[0][0] != 'module':
            return None
        return self.modules.resolve(module[0][1], node.attr)

    def constructed(self, func):
        """The source classes a call of func constructs, or None when it is not (only) a class call."""
        if self.modules is None:
            return None
        found = self._attribute(func) if isinstance(func, ast.Attribute) else (
            self.resolve(func.id) if isinstance(func, ast.Name) else None)
        if not found or any(binding[0] != 'class' for binding in found):
            return None
        return found

    def call_targets(self, func, names, modules=True):
        """The definitions a call may run: SAFE_BUILTINS, a set of sites, or None.

        A plain name (a module function or a safe builtin), a method of
        self/cls and (with modules) a function of an imported source module
        are resolved; any other receiver may be a foreign object.
        """
        name = lint.name(func)
        if isinstance(func, ast.Name) and not self._local(name):
            if name in SAFE_BUILTINS:
                return SAFE_BUILTINS
            return {site for site in names.get(name, ()) if '.' not in site.split(':', 1)[1]} or None
        if isinstance(func, ast.Attribute) and _root(func) in {'self', 'cls'} and \
                isinstance(func.value, ast.Name):
            return {site for site in names.get(name, ()) if '.' in site.split(':', 1)[1]} or None
        found = self._attribute(func) if modules else None
        if found and all(binding[0] == 'function' for binding in found):
            return {binding[1] for binding in found}
        return None

    def construction_targets(self, func, functions):
        """The __init__/__post_init__ sites a constructor call may run (empty when not a class call)."""
        return {site for binding in self.constructed(func) or ()
                for site in self.modules.construction_sites(binding[1], binding[2], functions)}

    def _binding_non_str(self, binding, names, proved, seen):
        if binding[0] != 'value':
            return True  # a function, class or module object
        return self.module_scope(binding[1], self.modules).non_str(binding[2], names, proved, seen)

    def _module_name_non_str(self, found, label, names, proved, seen):
        keys = {(binding[1] if binding[0] != 'function' else binding[1].split(':')[0], label)
                for binding in found}
        return bool(found) and not keys & seen and all(
            self._binding_non_str(binding, names, proved, seen | keys) for binding in found)

    def _selected_non_str(self, call, names, proved, seen):
        """max/min/next: the result is an operand, a comprehension element or the default."""
        args, keywords = call.args, {k.arg: k.value for k in call.keywords}
        if any(isinstance(a, ast.Starred) for a in args) or None in keywords:
            return False
        if lint.name(call.func) != 'next' and len(args) >= 2:
            # Comparing a str with a number raises, so a numeric operand leaves no str result.
            if any(isinstance(a, ast.Constant) and type(a.value) in (int, float) for a in args):
                return True
            operands = list(args)
        elif args and isinstance(args[0], COMPREHENSIONS):
            operands = [args[0].elt, *args[1:2]]
        else:
            return False
        if 'default' in keywords:
            operands.append(keywords['default'])
        return all(self.non_str(v, names, proved, seen) for v in operands)

    def non_str(self, expr, names, proved, seen=frozenset()):
        """Whether expr cannot be a non-empty str, given the sites proved so far (None: optimistic start)."""
        if expr is None or isinstance(expr, NON_STR_NODES):
            return True
        if isinstance(expr, ast.Constant):
            return not isinstance(expr.value, str) or not expr.value
        if isinstance(expr, ast.BoolOp):
            # `a and b` returns a only when a is falsy, and a falsy str is empty.
            operands = expr.values[-1:] if isinstance(expr.op, ast.And) else expr.values
            return all(self.non_str(v, names, proved, seen) for v in operands)
        if isinstance(expr, ast.IfExp):
            return all(self.non_str(v, names, proved, seen) for v in (expr.body, expr.orelse))
        if isinstance(expr, ast.BinOp):
            return isinstance(expr.op, NON_STR_OPERATORS) or all(
                self.non_str(v, names, proved, seen) for v in (expr.left, expr.right))
        if isinstance(expr, ast.Name):
            if self._local(expr.id):
                values = self.writes.get(expr.id)
                return (bool(values) and expr.id not in seen and expr.id not in self.params
                        and all(v is not None and self.non_str(v, names, proved, seen | {expr.id})
                                for v in values))
            found = self.resolve(expr.id)
            return found is not None and self._module_name_non_str(found, expr.id, names, proved, seen)
        if isinstance(expr, ast.Attribute):
            found = self._attribute(expr)
            return found is not None and self._module_name_non_str(found, expr.attr, names, proved, seen)
        if isinstance(expr, ast.Call):
            func = expr.func
            if isinstance(func, ast.Name) and func.id in SELECTING_BUILTINS and not self._local(func.id) \
                    and (self.modules is None or self.resolve(func.id) is None) \
                    and func.id not in self.imports:
                return self._selected_non_str(expr, names, proved, seen)
            classes = self.constructed(func)
            if classes:
                return all(self.modules.non_str_class(b[1], b[2]) for b in classes)
            targets = self.call_targets(func, names)
            if targets is SAFE_BUILTINS:
                return True
            return bool(targets) and (proved is None or targets <= proved)
        return False


def _nested_sites(functions):
    """The sites defined inside another function (their free names may be its locals)."""
    inner = {id(node) for function in functions.values() for node in ast.walk(function)
             if node is not function and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    return {site for site, function in functions.items() if id(function) in inner}


def _greatest(sites, keep):
    """The greatest fixpoint: start from every site, drop those whose callees fell."""
    proved = {site for site in sites if keep(site, None)}
    changed = True
    while changed:
        changed = False
        for site in sorted(proved):
            if not keep(site, proved):
                proved.discard(site)
                changed = True
    return proved


def proved_data(functions, names, origins, selected, seams, sources=None):
    """The selected sites proved to be observational data by the rules above.

    sources ({filename: text}, as the sites are keyed) enables the module-level resolution.
    """
    modules = _Modules(sources) if sources is not None else None
    nested = _nested_sites(functions)
    facts = {site: _Site(fn, site.split(':', 1)[0], modules, site in nested)
             for site, fn in functions.items()}
    constructions = {site: {target for func in facts[site].calls
                            for target in facts[site].construction_targets(func, functions)} - {site}
                     for site in functions}

    def callees(site, called):
        return {target for name in called for target in names.get(name, ()) if target != site} \
            | constructions[site]

    def no_seam(site, proved):
        called = facts[site].called
        if called & seams or any(name.startswith(SEAM_PREFIXES) for name in called):
            return False
        return proved is None or callees(site, called) <= proved

    def own_callees(site):
        # A function called through its module (module.f()) is not followed here, as before the
        # module-level resolution: following it would unprove sites whose module callees keep caches.
        found = (facts[site].call_targets(func, names, modules=False) for func in facts[site].calls)
        return {target for targets in found if targets and targets is not SAFE_BUILTINS
                for target in targets} - {site} | constructions[site]

    def no_mutation(site, proved):
        return not facts[site].problems and (proved is None or own_callees(site) <= proved)

    def no_key(site, proved):
        return all(facts[site].non_str(v, names, proved) for v in facts[site].values)

    candidates = {site for site in selected if set(origins[site]) == {'census'}}
    return candidates & _greatest(functions, no_seam) & _greatest(functions, no_mutation) \
        & _greatest(functions, no_key)
