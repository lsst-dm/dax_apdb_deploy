class FilterModule:
    def filters(self):
        return {"filter_milter": lambda x, y: x + y}
