class RelatedReadonlyFieldsMixin:
    related_readonly_config = {}

    def _generate_related_getter(self, rel, field, prefix=""):
        def _func(admin_self, obj):
            related = getattr(obj, rel)
            return getattr(related, field) if related else None

        _func.short_description = f"{prefix} {field.replace('_', ' ')}"
        return _func

    def _register_dynamic_readonly_fields(self):
        for rel, fields in self.related_readonly_config.items():
            for field in fields:
                method_name = f"get_{rel}_{field}"
                getter = self._generate_related_getter(rel, field, prefix=rel.capitalize())
                setattr(self.__class__, method_name, getter)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._register_dynamic_readonly_fields()

    def get_readonly_fields(self, request, obj=None):
        base = super().get_readonly_fields(request, obj)
        generated = [f"get_{rel}_{field}" for rel, fields in self.related_readonly_config.items() for field in fields]
        return list(base) + generated
