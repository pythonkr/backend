import collections.abc
import contextlib
import copy
import datetime
import types
import typing
import uuid

from django.apps.registry import apps as django_apps
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models.fields.files import FieldFile
from django.forms import model_to_dict


def arbitrary_value_to_basic_type(value: typing.Any) -> str | int | float | bool | None:
    """Convert an arbitrary value to a basic type that can be JSON serialized."""
    if isinstance(value, (int, float, bool)):
        return value
    elif isinstance(value, str):
        return value
    elif isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    elif isinstance(value, uuid.UUID):
        return str(value)
    elif isinstance(value, FieldFile):
        return value.name
    elif value is None:
        return None
    else:
        raise TypeError(f"Unsupported type for JSON serialization: {type(value)}")


def model_to_identifier(instance: models.Model) -> str:
    return f"mdl:{instance._meta.app_label}:{instance._meta.model_name}:{instance.pk}"


def identifier_to_model(identifier: str) -> models.Model | None:
    if not identifier.startswith("mdl:"):
        raise ValueError(f"Invalid model identifier: {identifier}")

    with contextlib.suppress(ValueError, LookupError, ObjectDoesNotExist):
        _, app_label, model_name, pk = identifier.split(":", 3)
        model_class: type[models.Model] = django_apps.get_model(app_label, model_name)
        return model_class.objects.get(pk=pk)

    return None


def _model_to_jsonable_dict(  # noqa: C901
    instance: models.Model,
    converted_models: dict[str, dict[str, typing.Any]],
    exclude: set[str] | None = None,
    nested: bool = False,
) -> dict:
    all_fields = {
        z for z in {f.name for f in instance._meta.fields} | set(instance._meta.fields_map.keys()) if z != "+"
    }
    exclude = {"created_at", "created_by", "updated_at", "updated_by", "deleted_at", "deleted_by"} | (exclude or set())

    model_dict = model_to_dict(instance, exclude=exclude)
    jsonable_model_dict: dict[str, str | int | float | bool | None] = {
        "id": str(instance.pk) if isinstance(instance.pk, uuid.UUID) else instance.pk,
        "pk": str(instance.pk) if isinstance(instance.pk, uuid.UUID) else instance.pk,
        "_meta": types.SimpleNamespace(
            app_label=instance._meta.app_label,
            model_name=instance._meta.model_name,
            verbose_name=instance._meta.verbose_name,
            verbose_name_plural=instance._meta.verbose_name_plural,
        ),
    }

    for field, value in model_dict.items():
        if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
            jsonable_model_dict[field] = value.isoformat()
        elif isinstance(value, (uuid.UUID, int, str)):
            # Is this field just a UUID | int | str, or is it a ForeignKey/OneToOneField?
            # django.forms.model_to_dict will return a UUID for Proxy model fields,
            # so we need to check if getattr(instance, field) is a model.Model instance.
            model_attr = getattr(instance, field, None)
            if isinstance(model_attr, models.Model):
                key = model_to_identifier(model_attr)

                jsonable_model_dict[f"{field}_id"] = (
                    str(model_attr.pk) if isinstance(model_attr.pk, uuid.UUID) else model_attr.pk
                )
                jsonable_model_dict[field] = key
                if key not in converted_models:
                    converted_models[key] = _model_to_jsonable_dict(model_attr, converted_models, None, True)
            else:
                # If it's just a UUID | int field, we can store it directly.
                jsonable_model_dict[field] = str(value) if isinstance(value, uuid.UUID) else value
        elif isinstance(value, models.Model):
            # simple ForeignKey or OneToOneField case.
            key = model_to_identifier(value)
            jsonable_model_dict[f"{field}_id"] = str(value.pk) if isinstance(value.pk, uuid.UUID) else value.pk
            jsonable_model_dict[field] = key
            if key not in converted_models:
                converted_models[key] = _model_to_jsonable_dict(value, converted_models, None, True)
        elif isinstance(value, (float, bool, str)) or value is None:
            jsonable_model_dict[field] = value
        elif isinstance(value, FieldFile):
            jsonable_model_dict[field] = value.name
        elif isinstance(value, collections.abc.Iterable):
            # Is this field a ManyToOneRel | ManyToManyField, or is it a json or array field?
            model_attr = getattr(instance, field, None)
            if isinstance(model_attr, models.manager.BaseManager):
                value = typing.cast(collections.abc.Iterable[models.Model], value)
                jsonable_value = []
                for v in value:
                    key = model_to_identifier(v)
                    jsonable_value.append(key)
                    if key not in converted_models:
                        converted_models[key] = _model_to_jsonable_dict(v, converted_models, None, True)
                jsonable_model_dict[field] = jsonable_value
            else:
                jsonable_model_dict[field] = [arbitrary_value_to_basic_type(v) for v in value]
        else:
            raise TypeError(f"Unsupported field type: {type(value)} for field '{field}'")

    if not nested:
        for leftover_field in all_fields - exclude - jsonable_model_dict.keys():
            # Possibly a many-to-many or many-to-one relation that was not included in the model_to_dict output.
            model_attr = getattr(instance, leftover_field, None)
            if not isinstance(model_attr, models.manager.BaseManager):
                continue
            if not (model_attr_objs := model_attr.all()):
                continue

            model_identifier_list = []
            for model in model_attr_objs:
                key = model_to_identifier(model)
                model_identifier_list.append(key)
                if key not in converted_models:
                    converted_models[key] = _model_to_jsonable_dict(model, converted_models, None, True)
            jsonable_model_dict[leftover_field] = model_identifier_list

    return jsonable_model_dict


def model_to_jsonable_dict(instance: models.Model):
    key = model_to_identifier(instance)
    converted_models: dict[str, dict[str, typing.Any]] = {}
    converted_models[key] = _model_to_jsonable_dict(instance, converted_models)
    return {"key": key, "model_data": converted_models}


def get_diff_data_from_jsonized_models(
    models_asis: dict[str, dict[str, typing.Any]],
    models_tobe: dict[str, dict[str, typing.Any]],
) -> dict[str, dict[str, typing.Any]]:
    diff_models_data: dict[str, dict[str, typing.Any]] = {}

    for model_identifier in set(models_asis.keys()).union(models_tobe.keys()):
        model_asis = models_asis.get(model_identifier, {})
        model_tobe = models_tobe.get(model_identifier, {})
        if not (model_asis and model_tobe):
            continue

        diff_models_data[model_identifier] = {}
        # Compare the contents of the models
        for field_name in set(model_asis.keys()).union(model_tobe.keys()):
            if field_name in model_asis and field_name not in model_tobe:
                continue
            if field_name not in model_asis and field_name in model_tobe:
                diff_models_data[model_identifier][field_name] = model_tobe[field_name]
                continue

            value_a = model_asis[field_name]
            value_b = model_tobe[field_name]
            if value_a == value_b:
                continue
            if value_a is not None and value_b is not None and type(value_a) != type(value_b):  # noqa: E721
                raise TypeError(
                    f"Type mismatch for field '{field_name}' in model '{model_identifier}': "
                    f"{type(value_a)} != {type(value_b)}"
                )
            diff_models_data[model_identifier][field_name] = value_b

    return {k: v for k, v in diff_models_data.items() if v}


def apply_diff_to_jsonized_models(
    models_asis: dict[str, dict[str, typing.Any]],
    models_diff: dict[str, dict[str, typing.Any]],
) -> dict[str, dict[str, typing.Any]]:
    updated_models = copy.deepcopy(models_asis)

    for model_identifier, diff_data in models_diff.items():
        if model_identifier not in updated_models:
            updated_models[model_identifier] = diff_data
            continue

        if not isinstance(updated_models[model_identifier], dict):
            raise TypeError(
                f"Expected a dict for model '{model_identifier}', got {type(updated_models[model_identifier])}"
            )

        for field_name, new_value in diff_data.items():
            updated_models[model_identifier][field_name] = new_value

    return updated_models


def json_to_simplenamespace(model_data: dict[str, dict[str, typing.Any]], key: str) -> types.SimpleNamespace:
    # Resolve models first
    resolved_models: dict[str, types.SimpleNamespace] = {}
    for model_identifier, model_datum in model_data.items():
        resolved_models[model_identifier] = types.SimpleNamespace(**model_datum)
    # link identifiers in resolved models to their SimpleNamespace instances
    for resolved_model in resolved_models.values():
        for attr_name, attr_value in resolved_model.__dict__.items():
            if isinstance(attr_value, str) and attr_value.startswith("mdl:"):
                setattr(resolved_model, attr_name, resolved_models[attr_value])
            elif isinstance(attr_value, list) and all(
                isinstance(item, str) and item.startswith("mdl:") for item in attr_value
            ):
                resolved_many_rel_models = [resolved_models[item] for item in attr_value]
                setattr(resolved_model, attr_name, resolved_many_rel_models)

    return resolved_models[key]


def apply_diff_to_model(models_data: dict[str, dict[str, typing.Any]]) -> list[models.Model]:
    result_instances: list[models.Model] = []

    for model_identifier, model_data in models_data.items():
        if not (model_instance := identifier_to_model(model_identifier)):
            raise ValueError(f"Model class not found for identifier: {model_identifier}")

        # Apply the data to the model instance
        for field_name, value in model_data.items():
            if isinstance(value, str) and value.startswith("mdl:"):
                # If the value is a model identifier, resolve it to a model instance
                if not (related_model_instance := identifier_to_model(value)):
                    raise ValueError(f"Related model not found for identifier: {value}")
                setattr(model_instance, field_name, related_model_instance)
            elif isinstance(value, list) and all(isinstance(item, str) and item.startswith("mdl:") for item in value):
                # If the value is a list of model identifiers, resolve them to model instances
                related_model_instances = [identifier_to_model(item) for item in value]
                if None in related_model_instances:
                    raise ValueError(f"One or more related models not found for identifiers: {value}")

                old_related_models = {item.pk: item for item in getattr(model_instance, field_name, [])}
                new_related_models = {item.pk: item for item in related_model_instances}

                field = getattr(model_instance, field_name)
                for del_pk in old_related_models.keys() - new_related_models.keys():
                    field.remove(old_related_models[del_pk])
                for add_pk in new_related_models.keys() - old_related_models.keys():
                    field.add(new_related_models[add_pk])
            else:
                setattr(model_instance, field_name, value)

        model_instance.save()
        result_instances.append(model_instance)

    return result_instances
