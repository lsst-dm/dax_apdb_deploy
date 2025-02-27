import re

import yaml
from ansible.errors import AnsibleFilterError


class FilterModule(object):
    def filters(self):
        return {
            "cleanup_cassandra_yaml": self.cleanup_cassandra_yaml,
            "merge_yaml_strings": self.merge_yaml_strings,
        }

    def cleanup_cassandra_yaml(self, cassandra_yaml_dict):
        if cassandra_yaml_dict.get("commitlog_sync", "") != "periodic":
            cassandra_yaml_dict = dict(cassandra_yaml_dict)
            cassandra_yaml_dict.pop("commitlog_sync_period", "")
        return cassandra_yaml_dict

    def merge_yaml_strings(self, yaml_str, yaml_str_2):
        """Update one YAML str with the contents of another."""

        try:
            yaml2 = yaml.safe_load(yaml_str_2)
        except Exception as exc:
            raise AnsibleFilterError(f"Failed to parse YAML string: {exc}") from exc

        lines = yaml_str.split("\n")
        for key, value in yaml2.items():
            add_if_missing = False
            if key.startswith("!"):
                add_if_missing = True
                key = key.lstrip("!")
            key_re = re.compile(f"^(# +)?{key} *:.*$")
            updated_lines = []
            found = False
            for line in lines:
                if found:
                    # Add all remaining lines without checking.
                    updated_lines.append(line)
                elif key_re.match(line):
                    if value == "__comment_out__":
                        if not line.startswith("#"):
                            line = "# " + line
                        updated_lines.append(line)
                    else:
                        updated_lines.append(f"{key}: {value}")
                    found = True
                else:
                    updated_lines.append(line)
            if not found:
                if add_if_missing:
                    updated_lines.append(f"{key}: {value}")
                else:
                    raise AnsibleFilterError(
                        f"Key {key} does not exist in the original YAML"
                    )
            lines = updated_lines

        return "\n".join(lines)
