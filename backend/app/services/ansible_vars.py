"""Write data for `ansible-playbook -e @file` so Ansible never templates it.

Ansible renders Jinja (`{{ lookup('pipe', ...) }}`) found in extra-vars values,
and lookups run on the console host. Everything the console passes to a playbook
is data (names, packages, compose files, test checks), so every string is
tagged `!unsafe`: Ansible then uses it verbatim and never evaluates it.
"""

from __future__ import annotations

import yaml


class _UnsafeDumper(yaml.SafeDumper):
    pass


def _unsafe_str(dumper: yaml.SafeDumper, value: str):
    return dumper.represent_scalar("!unsafe", value, style='"')


_UnsafeDumper.add_representer(str, _unsafe_str)


def dumps(data: dict) -> str:
    """YAML text with every string value tagged !unsafe (mapping keys stay plain)."""
    def keys_plain(obj):
        if isinstance(obj, dict):
            return {_Key(k): keys_plain(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [keys_plain(v) for v in obj]
        return obj
    return yaml.dump(keys_plain(data), Dumper=_UnsafeDumper, sort_keys=False, allow_unicode=True)


class _Key(str):
    """Mapping keys are our own identifiers; they stay untagged."""


_UnsafeDumper.add_representer(_Key, lambda d, v: d.represent_scalar("tag:yaml.org,2002:str", str(v)))


def write(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps(data))
