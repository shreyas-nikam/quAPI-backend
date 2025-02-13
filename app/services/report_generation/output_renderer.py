from pydantic import BaseModel, Field
from typing import Any, List


class IntroBlock(BaseModel):
    """Introduction block."""

    title: str = Field(..., description="The title of the report.")
    description: str = Field(..., description="The description of the report.")

class SummaryBlock(BaseModel):
    """Summary block."""

    summary: str = Field(..., description="The summary of the report.")

class ConclusionBlock(BaseModel):
    """Conclusion block."""

    conclusion: str = Field(..., description="The conclusion of the report.")



class TextBlock(BaseModel):
    """Text block."""

    text: str = Field(..., description="The text for this block.")


class ImageBlock(BaseModel):
    """Image block."""

    file_path: str = Field(..., description="File path to the image.")


class ReportOutput(BaseModel):
    """Data model for a report.

    Can contain a mix of text and image blocks. MUST contain at least one image block.
    MUST contain at least and at most one intro block, one summary block, and one conclusion block.

    """

    blocks: List[IntroBlock | SummaryBlock | ConclusionBlock | TextBlock | ImageBlock] = Field(
        ..., description="A list of text and image blocks."
    )

    def render(self) -> None:
        """Render as HTML on the page."""
        # for b in self.blocks:
        #     if isinstance(b, TextBlock):
        #          display(Markdown(b.text))
        #     elif isinstance(b, ImageBlock):
        #          display(Image(filename=b.file_path))
        #     elif isinstance(b, IntroBlock):
        #          display(Markdown(b.title))
        #          display(Markdown(b.description))
        #     elif isinstance(b, SummaryBlock):
        #          display(Markdown(b.summary))
        #     elif isinstance(b, ConclusionBlock):
        #          display(Markdown(b.conclusion))


    # blocks: List[TextBlock | ImageBlock] = Field(
    #     ..., description="A list of text and image blocks."
    # )

    # def render(self) -> None:
    #     """Render as HTML on the page."""
    #     for b in self.blocks:
    #         # TODO: render the block in a pdf
    #         if isinstance(b, TextBlock):
    #              display(Markdown(b.text))
    #         else:
    #              pass 
