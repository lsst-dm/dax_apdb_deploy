
import yaml

class Inventory:

    def __init__(self, file_obj: object):
        inventory = yaml.safe_load(stream=file_obj)
        assert isinstance(inventory, dict)
        self._inventory = inventory

    def get_host_names(self, group: str | None = None) -> list[str]:
        if not group:
            hosts = list(self._inventory.values())[0]["hosts"]
        else:
            hosts = self._inventory[group]["hosts"]

        return [item["ansible_host"] for item in hosts.values()]
