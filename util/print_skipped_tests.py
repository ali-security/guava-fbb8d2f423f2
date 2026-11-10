#!/usr/bin/env python3
"""Print surefire results per module: every skipped test with its reason, then totals.

Surefire 2.7.2 records JUnit/Truth assume() skips as a bare <skipped/> with no
message, so the reason is resolved from the test source: the assume()/assumeTrue
line in the skipped method's body.

Usage: print_skipped_tests.py <root dir containing the module dirs>
"""
import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

root = sys.argv[1] if len(sys.argv) > 1 else "."
modules = ["guava-testlib", "guava-tests"]

_source_cache = {}
_lines_cache = {}


def _read(path):
    lines = _lines_cache.get(path)
    if lines is None:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except OSError:
            lines = []
        _lines_cache[path] = lines
    return lines


def _test_files(module_dir):
    files = _source_cache.get(module_dir)
    if files is None:
        files = []
        for test_root in ("test", "src/test/java", "src"):
            base = os.path.join(module_dir, test_root)
            if os.path.isdir(base):
                files += glob.glob(os.path.join(base, "**", "*.java"), recursive=True)
        _source_cache[module_dir] = files
    return files


def _class_file(files, simple_name, pkg_path):
    """Source file declaring class simple_name, preferring the same package."""
    wanted = os.sep + simple_name + ".java"
    hits = [f for f in files if f.endswith(wanted)]
    hits.sort(key=lambda f: (pkg_path not in f, f))
    return hits[0] if hits else None


def _superclass(lines, simple_name):
    text = "".join(lines)
    m = re.search(r"class\s+" + re.escape(simple_name) + r"\b[^{]*?\bextends\s+([A-Za-z0-9_.]+)", text)
    return m.group(1).rsplit(".", 1)[-1] if m else None


def find_reason(module_dir, classname, method):
    # Surefire 2.7.2 names parameterized cases like
    #   addEdge_selfLoop[allowsSelfLoops=false, ...](com.google.common.graph.FooTest)
    # so the real class is the trailing "(...)" and the method is the text before "[" / "(".
    # For many SORTED-order network cases surefire stores that full string in the
    # testcase's classname attribute and a truncated copy in its name attribute.
    params = ""
    pattern = r"^([A-Za-z0-9_$]+)(\[.*\])?(?:\(([A-Za-z0-9_.$]+)\))?$"
    m = re.match(pattern, classname.strip())
    if not (m and m.group(3)):
        m = re.match(pattern, method.strip())
    if m:
        method = m.group(1)
        params = m.group(2) or ""
        if m.group(3):
            classname = m.group(3)
    else:
        method = re.split(r"[\[(]", method, 1)[0].strip()
    files = _test_files(module_dir)
    pkg_path = classname.rsplit(".", 1)[0].replace(".", os.sep)
    sigs = re.compile(r"void\s+" + re.escape(method) + r"\s*\(")
    # Walk the class -> superclass chain to the class that declares the test method.
    simple = classname.rsplit(".", 1)[-1].split("$")[0]
    seen = set()
    while simple and simple not in seen:
        seen.add(simple)
        path = _class_file(files, simple, pkg_path)
        if not path:
            break
        lines = _read(path)
        for i, line in enumerate(lines):
            if sigs.search(line):
                guards = []
                for body in lines[i + 1 : i + 40]:
                    if re.match(r"^  \}", body):
                        break
                    if "assume" in body:
                        guards.append(body.strip())
                if guards:
                    where = os.path.basename(path)
                    reason = "assumption not met in %s: %s" % (where, " ".join(guards))
                    if params:
                        reason += " (parameterization %s)" % params
                    return reason
        simple = _superclass(lines, simple)
    return "assumption not met (no explicit message recorded by surefire)"


grand = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
summaries = []
for module in modules:
    module_dir = os.path.join(root, module)
    reports = sorted(glob.glob(os.path.join(module_dir, "target", "surefire-reports", "TEST-*.xml")))
    totals = {"tests": 0, "failures": 0, "errors": 0, "skipped": 0}
    skipped_lines = []
    for report in reports:
        try:
            suite = ET.parse(report).getroot()
        except ET.ParseError as exc:
            print("WARN: cannot parse %s: %s" % (report, exc))
            continue
        for key in totals:
            totals[key] += int(float(suite.get(key, "0") or 0))
        for case in suite.iter("testcase"):
            skipped = case.find("skipped")
            if skipped is None:
                continue
            classname = case.get("classname", suite.get("name", ""))
            name = case.get("name", "")
            msg = (skipped.get("message") or (skipped.text or "")).strip()
            if not msg:
                msg = find_reason(module_dir, classname, name)
            skipped_lines.append("SKIPPED %s.%s -- %s" % (classname, name, msg))
    print("==== %s: skipped tests (%d) ====" % (module, len(skipped_lines)))
    for line in skipped_lines:
        print(line)
    summaries.append(
        "SUMMARY %s: reports=%d tests=%d passed=%d failures=%d errors=%d skipped=%d"
        % (
            module,
            len(reports),
            totals["tests"],
            totals["tests"] - totals["failures"] - totals["errors"] - totals["skipped"],
            totals["failures"],
            totals["errors"],
            totals["skipped"],
        )
    )
    for key in grand:
        grand[key] += totals[key]

for line in summaries:
    print(line)
print(
    "SUMMARY TOTAL (%s): tests=%d passed=%d failures=%d errors=%d skipped=%d"
    % (
        root,
        grand["tests"],
        grand["tests"] - grand["failures"] - grand["errors"] - grand["skipped"],
        grand["failures"],
        grand["errors"],
        grand["skipped"],
    )
)
