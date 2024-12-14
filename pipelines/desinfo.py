from __future__ import annotations

from typing import List, Union, Generator, Iterator
from schemas import OpenAIChatMessage
from pydantic import BaseModel
from openai import AzureOpenAI, RateLimitError
import os
from enum import Enum


class Pipeline:
    class Valves(BaseModel):
        pass

    def __init__(self):
        # Optionally, you can set the id and name of the pipeline.
        # Best practice is to not specify the id so that it can be automatically inferred from the filename, so that users can install multiple versions of the same pipeline.
        # The identifier must be unique across all pipelines.
        # The identifier must be an alphanumeric string that can include underscores or hyphens. It cannot contain spaces, special characters, slashes, or backslashes.
        # self.id = "pipeline_example"

        # The name of the pipeline.
        self.name = "DesinfoNavigator"
        endpoint =os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")

        self.llm = AzureOpenAI(
            max_retries=5,
            api_key=api_key,
            azure_endpoint=endpoint
        )

    async def on_startup(self):
        # This function is called when the server is started.
        pass

    async def on_shutdown(self):
        # This function is called when the server is stopped.
        self.llm.close()

    async def on_valves_updated(self):
        # This function is called when the valves are updated.
        pass

    async def inlet(self, body: dict, user: dict) -> dict:
        # This function is called before the OpenAI API request is made. You can modify the form data before it is sent to the OpenAI API.
        return body

    async def outlet(self, body: dict, user: dict) -> dict:
        # This function is called after the OpenAI API response is completed. You can modify the messages after they are received from the OpenAI API.
        return body

    def pipe(
        self, user_message: str, model_id: str, messages: List[dict], body: dict
    ) -> Union[str, Generator, Iterator]:
        # If you'd like to check for title generation, you can add the following check
        if body.get("title", False):
            print("Title Generation Request")

        if is_first_message(messages):
            strategies: list[AppliedStrategy] = identify_strategies(user_message)
            result = AppliedStrategy.construct_answer_from_list(strategies=strategies, original_text=user_message, openai_client=self.llm)
        else:
            # follow up
            completion = self.llm.chat.completions.create(
                model=self.deployment, messages=messages
            )
            result = completion.choices[0].message.content

        return result
    
class Strategy(Enum):
    FAKE_EXPERTS = "Pseudo-Experten"
    LOGICAL_FALLACIES = "Logischer Trugschluss"
    IMPOSSIBLE_EXPECTATIONS = "Unerfüllbare Erwartungen"
    CHERRY_PICKING = "Rosinenpickerei"
    CONSPIRACY_THEORIES = "Verschwörungsmythen"

    def get_description(self) -> str:
        if self == Strategy.FAKE_EXPERTS:
            return "Eine unqualifizierte Person oder Institution wird als Quelle glaubwürdiger Informationen präsentiert."
        elif self == Strategy.LOGICAL_FALLACIES:
            return "Argumente, bei denen sich die Schlussfolgerung nicht logischerweise aus den Prämissen ergibt. Auch bekannt als Non-Sequitur."
        elif self == Strategy.IMPOSSIBLE_EXPECTATIONS:
            return "Unrealistische Standards der Sicherheit fordern, bevor man die Wissenschaft akzeptiert."
        elif self == Strategy.CHERRY_PICKING:
            return "Sorgfältige Auswahl von Daten, die eine Position zu bestätigen scheinen, während andere Daten ignoriert werden, die dieser Position widersprechen."
        elif self == Strategy.CONSPIRACY_THEORIES:
            return "Eine Verschwörung zur Umsetzung eines üblen Plans vermuten, wie das Verbergen der Wahrheit oder das Weitergeben von Falschinformationen."
        else:
            raise NotImplementedError(f"{self} not implemented.")
    
class AppliedStrategy(BaseModel):
    content: str
    offset: int
    strategy: Strategy

    @classmethod
    def return_example_list(cls) -> list[AppliedStrategy]:
        return [
            AppliedStrategy(
                content="Das Klima hat sich in der Vergangenheit wegen natürlichen Ursachen verändert, also haben die heutigen Veränderungen ebenfalls natürliche Ursachen.",
                offset=0,
                strategy=Strategy.LOGICAL_FALLACIES
            ),
            AppliedStrategy(
                content="Wissenschaftler können nicht einmal das Wetter in der nächsten Woche vorhersagen. Wie sollen sie also das Wetter in 100 Jahren vorhersagen können?",
                offset=0,
                strategy=Strategy.IMPOSSIBLE_EXPECTATIONS
            )
        ]
    
    def create_action(self, original_text: str, openai_client: AzureOpenAI) -> str:
        return "PLACEHOLDER_ACTION"
    
    def stringify_long(self, original_text: str, openai_client: AzureOpenAI) -> str:
        return f"""\t- Definition: {self.strategy.get_description()}
        \t- Passage: {self.content}
        \t- Individueller Denkauftrag: {self.create_action(original_text=original_text, openai_client=openai_client)}"""
    
    def stringify_short(self) -> str:
        return f"\t- {self.strategy.name}"

    @classmethod
    def construct_answer_from_list(cls, strategies: list[AppliedStrategy], original_text: str, openai_client: AzureOpenAI) -> str:
        individual_strategies_long = "\n\n".join([strategy.stringify_long(original_text, openai_client) for strategy in strategies])
        individual_strategies_short = "\n".join([strategy.stringify_short() for strategy in strategies])
        return f"""
        AMPEL

        Es liegen folgende Merkmale von Desinformation vor
        {individual_strategies_short}

        Individuelle Anweisungen
        {individual_strategies_long}
        """
    
AppliedStrategy.model_rebuild()

def identify_strategies(user_message: str) -> list[AppliedStrategy]:
    """ identifies strategies from a user message """
    return AppliedStrategy.return_example_list()

def is_first_message(messages: list[dict]) -> bool:
    return len(messages) == 1