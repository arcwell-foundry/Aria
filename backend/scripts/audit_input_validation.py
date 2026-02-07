"""Audit script to check all Pydantic models have proper validation.

Run: python backend/scripts/audit_input_validation.py
"""

import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple


class ValidationIssue(NamedTuple):
    """Represents a validation issue found in the code."""
    file_path: str
    line_no: int
    model_name: str
    field_name: str
    field_type: str
    issue: str
    severity: str  # "critical" or "warning"


def check_pydantic_model_validation(file_path: Path) -> list[ValidationIssue]:
    """Check a file for Pydantic models with validation issues."""
    issues = []

    with open(file_path) as f:
        content = f.read()
        tree = ast.parse(content, filename=str(file_path))

    # Track imports to know what types are being used
    imported_types = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "pydantic" in node.module:
                for alias in node.names:
                    imported_types.add(alias.asname or alias.name)

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            # Check if it's a Pydantic model
            is_pydantic = False
            for base in node.bases:
                base_name = base.id if isinstance(base, ast.Name) else ""
                if base_name in ["BaseModel", "Field"] or "Model" in base_name:
                    is_pydantic = True
                    break

            if not is_pydantic:
                continue

            for item in node.body:
                if not isinstance(item, ast.AnnAssign):
                    continue

                # Get field name
                var_name = item.target.id if isinstance(item.target, ast.Name) else "?"

                # Get field type annotation
                field_type = ""
                if item.annotation:
                    if isinstance(item.annotation, ast.Name):
                        field_type = item.annotation.id
                    elif isinstance(item.annotation, ast.Subscript):
                        if isinstance(item.annotation.value, ast.Name):
                            field_type = item.annotation.value.id
                    elif isinstance(item.annotation, ast.Constant):
                        field_type = str(item.annotation.value)

                # Check if field has Field() with constraints
                has_field_call = isinstance(item.value, ast.Call)
                has_constraints = False
                has_default = False

                if has_field_call:
                    call = item.value
                    if isinstance(call.func, ast.Name) and call.func.id == "Field":
                        # Has Field() - check for constraints
                        for kw in call.keywords:
                            if kw.arg in ["min_length", "max_length", "ge", "le", "gt", "lt", "pattern", "regex"]:
                                has_constraints = True
                            if kw.arg in ["default", "default_factory", "alias"]:
                                has_default = True

                # Check for specific validation issues

                # Issue 1: String fields without length constraints
                if field_type in ["str", "string"] and has_field_call and not has_constraints:
                    # Allow strings with pattern or other constraints
                    if not any(kw.arg in ["pattern", "regex"] for kw in item.value.keywords if isinstance(item.value, ast.Call)):
                        issues.append(ValidationIssue(
                            file_path=str(file_path),
                            line_no=item.lineno,
                            model_name=node.name,
                            field_name=var_name,
                            field_type=field_type,
                            issue="String field without min_length/max_length constraints",
                            severity="critical"
                        ))

                # Issue 2: String fields without any Field() call
                if field_type in ["str", "string"] and not has_field_call:
                    issues.append(ValidationIssue(
                        file_path=str(file_path),
                        line_no=item.lineno,
                        model_name=node.name,
                        field_name=var_name,
                        field_type=field_type,
                        issue="String field without Field() validation",
                        severity="warning"
                    ))

                # Issue 3: Email fields should use EmailStr
                if "email" in var_name.lower() and field_type == "str":
                    issues.append(ValidationIssue(
                        file_path=str(file_path),
                        line_no=item.lineno,
                        model_name=node.name,
                        field_name=var_name,
                        field_type=field_type,
                        issue="Email field should use EmailStr type",
                        severity="critical"
                    ))

                # Issue 4: Optional fields without Field()
                if item.annotation and isinstance(item.annotation, ast.Subscript):
                    if isinstance(item.annotation.value, ast.Name) and item.annotation.value.id == "Optional":
                        if not has_field_call and item.value is None:
                            issues.append(ValidationIssue(
                                file_path=str(file_path),
                                line_no=item.lineno,
                                model_name=node.name,
                                field_name=var_name,
                                field_type="Optional",
                                issue="Optional field without Field(default=None)",
                                severity="warning"
                            ))

    return issues


def main():
    """Run the audit."""
    routes_dir = Path("backend/src/api/routes")
    all_issues = []
    critical_issues = []

    if not routes_dir.exists():
        print(f"Error: Routes directory {routes_dir} does not exist")
        sys.exit(1)

    for py_file in sorted(routes_dir.glob("*.py")):
        if py_file.name != "__init__.py":
            issues = check_pydantic_model_validation(py_file)
            all_issues.extend(issues)
            critical_issues.extend([i for i in issues if i.severity == "critical"])

    # Group issues by file for better reporting
    issues_by_file = {}
    for issue in all_issues:
        if issue.file_path not in issues_by_file:
            issues_by_file[issue.file_path] = []
        issues_by_file[issue.file_path].append(issue)

    if all_issues:
        print(f"\nInput Validation Audit Results")
        print("=" * 80)
        print(f"Total Issues Found: {len(all_issues)}")
        print(f"Critical Issues: {len(critical_issues)}")
        print(f"Warnings: {len(all_issues) - len(critical_issues)}")
        print("=" * 80)

        for file_path, issues in sorted(issues_by_file.items()):
            # Make path relative for cleaner output
            try:
                rel_path = Path(file_path).relative_to(Path.cwd())
            except ValueError:
                rel_path = Path(file_path)
            print(f"\n{rel_path}:")

            # Group by severity
            critical = [i for i in issues if i.severity == "critical"]
            warnings = [i for i in issues if i.severity == "warning"]

            if critical:
                print("  CRITICAL:")
                for issue in critical:
                    print(f"    Line {issue.line_no}: {issue.model_name}.{issue.field_name}")
                    print(f"      Type: {issue.field_type}")
                    print(f"      Issue: {issue.issue}")

            if warnings:
                print("  WARNING:")
                for issue in warnings:
                    print(f"    Line {issue.line_no}: {issue.model_name}.{issue.field_name}")
                    print(f"      Type: {issue.field_type}")
                    print(f"      Issue: {issue.issue}")

        print("\n" + "=" * 80)
        print("Recommendations:")
        print("  - Add min_length/max_length to string fields")
        print("  - Use EmailStr for email validation")
        print("  - Add pattern constraints for formatted strings (phone, IDs, etc.)")
        print("  - Use Field(default=...) for optional fields")
        print("=" * 80)

        sys.exit(1)
    else:
        print("\n✓ All Pydantic models have validation constraints!")
        sys.exit(0)


if __name__ == "__main__":
    main()
