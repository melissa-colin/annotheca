"""Validated shapes shared by the HTTP API and the project bundles."""

from typing import Annotated, Any, Literal

import pydantic

Name = Annotated[str, pydantic.StringConstraints(
    strip_whitespace=True, min_length=1, max_length=80)]
Color = Annotated[str, pydantic.StringConstraints(pattern=r'^#[0-9a-fA-F]{6}$')]


class Annotation(pydantic.BaseModel):
    """A highlight or a note; coordinates are fractions of the page size.

    A highlight's geometry is a list of [x, y, width, height] rectangles;
    a note's is its [x, y] top-left corner.
    """
    kind: Literal['highlight', 'note']
    page: int = pydantic.Field(ge=1)
    color: Color
    geometry: list[Any]
    quote: str = ''
    body: str = ''
