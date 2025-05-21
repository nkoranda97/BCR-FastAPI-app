from pydantic import BaseModel
from typing import List


class GeneSelect(BaseModel):
    """Form for selecting genes in the logo view."""

    genes: List[str]

    def __init__(self, genes: List[str]):
        super().__init__(genes=genes)

    @property
    def gene(self):
        """Get the gene field for the form."""
        return self.genes[0] if self.genes else None

    @property
    def label(self):
        """Get the label for the gene field."""
        return "Select Gene"
