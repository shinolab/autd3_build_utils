import ast
import re


class PyiGenerator(ast.NodeVisitor):
    def __init__(self) -> None:
        self.class_defs = []
        self.imports = []
        self.should_generate = False

    def get_generic_type(self, base: list[str]) -> str | None:
        r = re.compile(r"Generic\[(.*)\]")
        for item in base:
            if match := r.match(item):
                return match.group(1)
        return None

    def visit_Import(self, node) -> None:  # noqa: ANN001, N802
        for alias in node.names:
            import_name = f"import {alias.name}"
            if alias.asname:
                import_name += f" as {alias.asname}"
            self.imports.append(import_name)

    def visit_ImportFrom(self, node) -> None:  # noqa: ANN001, N802
        for alias in node.names:
            import_name = f"from {node.module} import {alias.name}"
            if alias.asname:
                import_name += f" as {alias.asname}"
            self.imports.append(import_name)

    def visit_ClassDef(self, node) -> None:  # noqa: ANN001, C901, N802, PLR0912, PLR0915
        class_name = node.name
        base_classes = [self._get_type_annotation(base) for base in node.bases]
        full_class_name = f"{class_name}[{self.get_generic_type(base_classes)}]" if self.get_generic_type(base_classes) is not None else class_name
        attributes = []
        async_methods = []
        methods = []
        staticmethods = []
        classmethods = []
        properties = []

        for body_item in node.body:
            match body_item:
                case ast.AnnAssign(target=ast.Name(id=attr_name), annotation=annotation):
                    if not attr_name.startswith("_param_") and not attr_name.startswith("_prop_"):
                        attr_type = self._get_type_annotation(annotation)
                        attributes.append((attr_name, attr_type))
                case ast.AsyncFunctionDef(
                    name=method_name,
                    args=ast.arguments(args=args, defaults=defaults),
                    returns=returns,
                    decorator_list=decorators,
                ):
                    return_type = self._get_type_annotation(returns)
                    args = [(arg.arg, self._get_type_annotation(arg.annotation)) for arg in args[1:]]
                    defaults = [self._get_value_expr(d) for d in defaults]
                    async_methods.append((method_name, args, defaults, return_type))
                case ast.FunctionDef(
                    name=method_name,
                    args=ast.arguments(posonlyargs=posonlyargs, args=args, defaults=defaults),
                    returns=returns,
                    decorator_list=decorators,
                ):
                    if any(d.id == "property" for d in decorators if isinstance(d, ast.Name)):
                        return_type = self._get_type_annotation(returns)
                        properties.append((method_name, return_type))
                    elif any(d.id == "staticmethod" for d in decorators if isinstance(d, ast.Name)):
                        return_type = self._get_type_annotation(returns)
                        args = [(arg.arg, self._get_type_annotation(arg.annotation)) for arg in args]
                        staticmethods.append((method_name, args, return_type))
                    elif any(d.id == "classmethod" for d in decorators if isinstance(d, ast.Name)):
                        return_type = self._get_type_annotation(returns)
                        args = [(arg.arg, self._get_type_annotation(arg.annotation)) for arg in args[1:]]
                        classmethods.append((method_name, args, return_type))
                    else:
                        return_type = self._get_type_annotation(returns)
                        posonlyargs = [(arg.arg, self._get_type_annotation(arg.annotation)) for arg in posonlyargs[1:]]
                        args = [(arg.arg, self._get_type_annotation(arg.annotation)) for arg in args[1:]]
                        defaults = [self._get_value_expr(d) for d in defaults]
                        methods.append((method_name, posonlyargs, args, defaults, return_type))

        if any(d.id == "builder" for d in node.decorator_list if isinstance(d, ast.Name)):
            self.should_generate = True
            fields = {}
            for class_node in node.body:
                match class_node:
                    case ast.AnnAssign(target=ast.Name(id=attr_name), annotation=annotation):
                        fields[class_node.target.id] = self._get_type_annotation(class_node.annotation)

            for field_name, field_type in fields.items():
                if field_name.startswith("_param_"):
                    prop_name = field_name[7:]
                    if field_name.endswith("_u8"):
                        prop_name = prop_name[:-3]
                    properties.append((prop_name, field_type))
                    if field_type == "EmitIntensity":
                        field_type = "int | EmitIntensity"  # noqa: PLW2901
                    elif field_type == "Phase":
                        field_type = "int | Phase"  # noqa: PLW2901
                    methods.append(
                        (
                            f"with_{prop_name}",
                            [],
                            [(prop_name, field_type)],
                            [],
                            full_class_name,
                        ),
                    )

                if field_name.startswith("_prop_"):
                    properties.append((field_name[6:], field_type))

        if any(d.id == "gain" for d in node.decorator_list if isinstance(d, ast.Name)):
            self.should_generate = True

            if class_name != "Cache":
                self.imports.append("from pyautd3.gain.cache import Cache")
                methods.append(
                    (
                        "with_cache",
                        [],
                        [],
                        [],
                        f"Cache[{full_class_name}]",
                    ),
                )

        if any(d.id == "modulation" for d in node.decorator_list if isinstance(d, ast.Name)):
            self.should_generate = True

            if class_name != "Cache":
                self.imports.append("from pyautd3.modulation.cache import Cache")
                methods.append(
                    (
                        "with_cache",
                        [],
                        [],
                        [],
                        f"Cache[{full_class_name}]",
                    ),
                )
            if class_name != "Fir":
                self.imports.append("from pyautd3.modulation.fir import Fir")
                self.imports.append("from collections.abc import Iterable")
                methods.append(
                    (
                        "with_fir",
                        [],
                        [
                            ("iterable", "Iterable[float]"),
                        ],
                        [],
                        f"Fir[{full_class_name}]",
                    ),
                )
            if class_name != "RadiationPressure":
                self.imports.append("from pyautd3.modulation.radiation_pressure import RadiationPressure")
                methods.append(
                    (
                        "with_radiation_pressure",
                        [],
                        [],
                        [],
                        f"RadiationPressure[{full_class_name}]",
                    ),
                )

        if any(d.id == "datagram" for d in node.decorator_list if isinstance(d, ast.Name)):
            self.should_generate = True

            if class_name != "DatagramWithTimeout":
                self.imports.append("from pyautd3.utils import Duration")
                self.imports.append("from pyautd3.driver.datagram.with_timeout import DatagramWithTimeout")
                methods.append(
                    (
                        "with_timeout",
                        [],
                        [
                            ("timeout", "Duration | None"),
                        ],
                        [],
                        f"DatagramWithTimeout[{full_class_name}]",
                    ),
                )
            if class_name != "DatagramWithParallelThreshold":
                self.imports.append("from pyautd3.driver.datagram.with_parallel_threshold import DatagramWithParallelThreshold")
                methods.append(
                    (
                        "with_parallel_threshold",
                        [],
                        [
                            ("threshold", "int | None"),
                        ],
                        [],
                        f"DatagramWithParallelThreshold[{full_class_name}]",
                    ),
                )
        if any(d.id == "datagram_with_segment" for d in node.decorator_list if isinstance(d, ast.Name)):
            self.should_generate = True

            self.imports.append("from pyautd3.native_methods.autd3capi_driver import TransitionModeWrap")
            self.imports.append("from pyautd3.native_methods.autd3_core import Segment")
            self.imports.append("from pyautd3.driver.datagram.with_segment import DatagramWithSegment")
            methods.append(
                (
                    "with_segment",
                    [],
                    [
                        ("segment", "Segment"),
                        ("transition_mode", "TransitionModeWrap | None"),
                    ],
                    [],
                    f"DatagramWithSegment[{full_class_name}]",
                ),
            )

        self.class_defs.append(
            (
                class_name,
                full_class_name,
                base_classes,
                attributes,
                async_methods,
                methods,
                staticmethods,
                classmethods,
                properties,
            ),
        )

    def _get_value_expr(self, expr):  # noqa: ANN001, ANN202
        match expr:
            case ast.Constant(value=value):
                return value
            case ast.Name(id=id):
                return id
            case _:
                return "None"

    def _get_type_annotation(self, annotation):  # noqa: ANN001, ANN202, PLR0911
        match annotation:
            case ast.Name(id=id):
                return id
            case ast.Constant(value=value):
                return str(value)
            case ast.Subscript(value=value, slice=sl):
                return f"{self._get_type_annotation(value)}[{self._get_type_annotation(sl)}]"
            case ast.Tuple(elts=elts):
                return f"{', '.join([self._get_type_annotation(elt) for elt in elts])}"
            case ast.List(elts=elts):
                return f"[{', '.join([self._get_type_annotation(elt) for elt in elts])}]"
            case ast.BinOp(left=left, op=ast.BitOr(), right=right):
                return f"{self._get_type_annotation(left)} | {self._get_type_annotation(right)}"
            case ast.Attribute(value=value, attr=attr):
                return f"{self._get_type_annotation(value)}.{attr}"
            case None:
                return "None"
            case _:
                return ""

    def generate_pyi(self) -> str:
        lines = []
        for class_name, full_class_name, base_classes, attributes, async_methods, methods, staticmethods, classmethods, properties in self.class_defs:
            lines.append(f"class {class_name}({', '.join(base_classes)}):")
            for attr_name, attr_type in attributes:
                lines.append(f"    {attr_name}: {attr_type}")
            for method_name, args, defaults, return_type in async_methods:
                defaults = ["None"] * (len(args) - len(defaults)) + defaults  # noqa: PLW2901
                args_str = ", ".join(
                    [f"{name}: {ty}" + (f" = {default}" if default != "None" else "") for (name, ty), default in zip(args, defaults, strict=True)],
                )
                lines.append(f"    async def {method_name}(self: {full_class_name}, {args_str}) -> {return_type}: ...")
            for method_name, posonlyargs, args, defaults, return_type in methods:
                defaults = ["None"] * (len(args) - len(defaults)) + defaults  # noqa: PLW2901
                posonlyargs_str = ", ".join([f"{name}: {ty}" for name, ty in posonlyargs])
                args_str = ", ".join(
                    [f"{name}: {ty}" + (f" = {default}" if default != "None" else "") for (name, ty), default in zip(args, defaults, strict=True)],
                )
                if posonlyargs_str:
                    args_str = posonlyargs_str + ", /, " + args_str
                if method_name == "__new__":
                    lines.append(f"    def {method_name}(cls, {args_str}) -> {return_type}: ...")
                elif method_name == "__init__" and class_name == "FociSTM":
                    lines.append(f"    def {method_name}(self: {class_name}, {args_str}) -> {return_type}: ...")
                else:
                    lines.append(f"    def {method_name}(self: {full_class_name}, {args_str}) -> {return_type}: ...")
            for method_name, args, return_type in staticmethods:
                args_str = ", ".join([f"{name}: {ty}" for name, ty in args])
                lines.append("    @staticmethod")
                lines.append(f"    def {method_name}({args_str}) -> {return_type}: ...")
            for method_name, args, return_type in classmethods:
                args_str = ", ".join([f"{name}: {ty}" for name, ty in args])
                lines.append("    @classmethod")
                lines.append(f"    def {method_name}(cls, {args_str}) -> {return_type}: ...")
            for prop_name, prop_type in properties:
                lines.append("    @property")
                lines.append(f"    def {prop_name}(self: {full_class_name}) -> {prop_type}: ...")
            lines.append("")
        return "\n".join(lines)
