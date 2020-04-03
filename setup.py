#!/usr/bin/env python3

import ast
import setuptools


def attr(file, name):
	"""Read the constant value of a global variable from a Python file without importing/executing it.
	
	The variable in question must be assigned a constant literal
	(as understood by :func:`ast.literal_eval`)
	in a simple assignment.
	The variable *should* only be assigned once
	(later assignments are silently ignored).
	
	Based on https://github.com/pypa/setuptools/issues/1960#issue-547330414.
	"""
	
	with open(file, "rb") as f:
		module = ast.parse(f.read())
	
	for node in ast.iter_child_nodes(module):
		if (
			isinstance(node, ast.Assign)
			and len(node.targets) == 1
			and isinstance(node.targets[0], ast.Name)
			and node.targets[0].id == name
		):
			return ast.literal_eval(node.value)
	else:
		raise ValueError(f"No simple assignment of variable {name!r} found in {file!r}")


setuptools.setup(
	# Read the version number from the module source code without importing or executing it.
	# This is necessary because at the time that setup.py is executed,
	# the dependencies necessary to import rsrcfork may not be installed yet.
	version=attr("rsrcfork/__init__.py", "__version__"),
)
