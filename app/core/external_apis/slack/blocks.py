import dataclasses
import typing


class SlackChildBlockType(typing.TypedDict):
    type: typing.Literal["plain_text", "mrkdwn"]
    text: str
    emoji: typing.NotRequired[typing.Literal[True]]
    title: typing.NotRequired[str]


class SlackAccessoryBlockType(typing.TypedDict):
    type: str
    text: typing.NotRequired[SlackChildBlockType]
    url: typing.NotRequired[str]


class SlackParentBlockType(typing.TypedDict):
    type: str
    text: typing.NotRequired[SlackChildBlockType]
    fields: typing.NotRequired[list[SlackChildBlockType]]
    accessory: typing.NotRequired[SlackAccessoryBlockType]


class SlackBlocksType(typing.TypedDict):
    blocks: list[SlackParentBlockType]


@dataclasses.dataclass
class SlackChildBlock:
    text: str
    type: typing.Literal["plain_text", "mrkdwn"] = "plain_text"

    def to_dict(self) -> SlackChildBlockType:
        result = SlackChildBlockType(type=self.type, text=self.text)
        if self.type == "plain_text":
            result["emoji"] = True
        return result


@dataclasses.dataclass
class SlackPlainTextChildBlock(SlackChildBlock):
    type: typing.Literal["plain_text"] = "plain_text"


@dataclasses.dataclass
class SlackMarkDownChildBlock(SlackChildBlock):
    type: typing.Literal["mrkdwn"] = "mrkdwn"


@dataclasses.dataclass
class SlackCodeChildBlock(SlackMarkDownChildBlock):
    title: str = ""

    def __post_init__(self) -> None:
        code_title = f"*{self.title}*\n" if self.title else ""
        self.text = f"{code_title}```{self.text}```"


@dataclasses.dataclass
class SlackAccessoryBlock:
    type: str
    text: SlackChildBlock | None = None

    def to_dict(self) -> SlackAccessoryBlockType:
        result = SlackAccessoryBlockType(type=self.type)
        if self.text:
            result["text"] = self.text.to_dict()
        return result


@dataclasses.dataclass
class SlackURLButtonAccessoryBlock(SlackAccessoryBlock):
    url: str = ""
    type: typing.Literal["button"] = "button"
    text: SlackChildBlock | None = None

    def to_dict(self) -> SlackAccessoryBlockType:
        return super().to_dict() | {"url": self.url}


@dataclasses.dataclass
class SlackParentBlock:
    type: str
    text: SlackChildBlock | None = None
    fields: list[SlackChildBlock] | None = None

    def __post_init__(self) -> None:
        if not (self.text or self.fields):
            raise ValueError("At least one of text or fields must be set!")

    def to_dict(self) -> SlackParentBlockType:
        result = SlackParentBlockType(type=self.type)
        if self.text:
            result["text"] = self.text.to_dict()
        if self.fields:
            result["fields"] = [f.to_dict() for f in self.fields]
        return result


@dataclasses.dataclass
class SlackHeaderParentBlock(SlackParentBlock):
    type: str = "header"

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.fields:
            raise ValueError("header block only allows text, not fields!")
        if self.text.type != "plain_text":
            raise ValueError("header block only allows plain_text text block!")


@dataclasses.dataclass
class SlackSectionParentBlock(SlackParentBlock):
    type: str = "section"
    accessory: SlackAccessoryBlock | None = None

    def to_dict(self) -> SlackParentBlockType:
        result = super().to_dict()
        if self.accessory:
            result["accessory"] = self.accessory.to_dict()
        return result


@dataclasses.dataclass
class SlackBlocks:
    blocks: list[SlackParentBlock]

    def to_dict(self) -> SlackBlocksType:
        return SlackBlocksType(blocks=[b.to_dict() for b in self.blocks])
