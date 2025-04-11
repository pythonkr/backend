import argparse
import json
import pathlib
import typing

import boto3

if typing.TYPE_CHECKING:
    import mypy_boto3_ssm

ssm_client: "mypy_boto3_ssm.SSMClient" = boto3.client("ssm")


class ValueDiff(typing.NamedTuple):
    old: str | None
    new: str | None


class ParameterDiffCollection(typing.NamedTuple):
    updated: dict[str, ValueDiff]
    created: dict[str, ValueDiff]
    deleted: dict[str, ValueDiff]


def read_json_file(json_file: pathlib.Path, stage: str) -> dict[str, str]:
    if not (data_groups := json.loads(json_file.read_text())) or not isinstance(data_groups, dict):
        raise ValueError("JSON 파일이 잘못되었습니다.")

    if not (data := typing.cast(dict[str, typing.Any], data_groups.get(stage))):
        raise ValueError("JSON 파일에 해당 스테이지의 파라미터가 없습니다.")

    if not all(isinstance(k, str) and isinstance(v, (str, int, float, bool)) for k, v in data.items()):
        # object / array / null is not allowed here
        raise ValueError("JSON 파일의 파라미터가 잘못되었습니다.")

    return {k: str(v) for k, v in data.items()}


def read_parameter_store(project_name: str, stage: str) -> dict[str, str]:
    parameters: dict[str, str] = {}
    next_token = ""  # nosec: B105
    while next_token is not None:
        result = ssm_client.get_parameters_by_path(
            Path=f"/{project_name}/{stage}",
            MaxResults=10,
            **({"NextToken": next_token} if next_token else {}),
        )
        parameters.update({p["Name"].split("/")[-1]: p["Value"] for p in result["Parameters"]})
        next_token = result.get("NextToken")
    return parameters


def get_parameter_diff(old_parameters: dict[str, str], new_parameters: dict[str, str]) -> ParameterDiffCollection:
    created, updated, deleted = {}, {}, {}

    for fields in old_parameters.keys() | new_parameters.keys():
        value = ValueDiff(old=old_parameters.get(fields), new=new_parameters.get(fields))
        if value.old != value.new:
            if value.old is None:
                created[fields] = value
            elif value.new is None:
                deleted[fields] = value
            else:
                updated[fields] = value

    return ParameterDiffCollection(updated=updated, created=created, deleted=deleted)


def update_parameter_store(project_name: str, stage: str, diff: ParameterDiffCollection) -> None:
    for field, values in {**diff.created, **diff.updated}.items():
        ssm_client.put_parameter(
            Name=f"/{project_name}/{stage}/{field}",
            Value=values.new,
            Type="String",
            Overwrite=True,
        )

    if diff.deleted:
        ssm_client.delete_parameters(Names=[f"/{project_name}/{stage}/{field}" for field in diff.deleted.keys()])


def main(project_name: str, stage: str, json_file: pathlib.Path) -> None:
    if not all([json_file.is_file(), project_name, stage]):
        raise ValueError("인자를 확인해주세요.")

    old_params = read_parameter_store(project_name, stage)
    new_params = read_json_file(json_file, stage)
    diff = get_parameter_diff(old_params, new_params)

    print(f"Updated: '{', '.join(diff.updated.keys())}'")
    print(f"Created: '{', '.join(diff.created.keys())}'")
    print(f"Deleted: '{', '.join(diff.deleted.keys())}'")
    update_parameter_store(project_name, stage, diff)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project_name", type=str)
    parser.add_argument("--stage", type=str)
    parser.add_argument("--json_file", type=pathlib.Path)

    args = parser.parse_args()
    main(project_name=args.project_name, stage=args.stage, json_file=args.json_file)
