from __future__ import annotations

from abc import ABC, abstractmethod

from vision_ai.schema import VisionAIRequest, VisionAIResponse


class VisionAIProvider(ABC):
    name = "vision-ai"

    @abstractmethod
    def review_page(self, request: VisionAIRequest) -> VisionAIResponse:
        raise NotImplementedError
