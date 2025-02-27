class FilterModule(object):
    def filters(self):
        return {"cleanup_cassandra_yaml": self.cleanup_cassandra_yaml}

    def cleanup_cassandra_yaml(self, cassandra_yaml_dict):
        if cassandra_yaml_dict.get("commitlog_sync") != "periodic":
            cassandra_yaml_dict = dict(cassandra_yaml_dict)
            cassandra_yaml_dict.pop("commitlog_sync_period", None)
        return cassandra_yaml_dict
