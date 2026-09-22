"""Suite-wide setup.

The toolbox fixture that lived here is gone with the mechanism it guarded: the
bench no longer bind-mounts gdb or a copy of the target into a published image,
because the agent images ship both. Nothing in the suite reaches a registry.
"""
