from __future__ import annotations

import instructor
import pandas as pd
from typing import List, Union, Generator, Iterator
from pydantic import BaseModel, Field
from openai import AzureOpenAI
import os
from enum import Enum

deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")


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
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")

        self.llm = AzureOpenAI(max_retries=5, api_key=api_key, azure_endpoint=endpoint)
        self.strategy_examples = get_strategy_examples()

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
            strategies: list[AppliedStrategy] = identify_strategies(
                user_message, openai_client=self.llm
            )
            result = AppliedStrategy.construct_answer_from_list(
                strategies=strategies,
                original_text=user_message,
                openai_client=self.llm,
            )
        else:
            # follow up
            completion = self.llm.chat.completions.create(
                model=deployment, messages=messages
            )
            result = completion.choices[0].message.content

        return result


fake_experts_desc = "Eine unqualifizierte Person oder Institution wird als Quelle glaubwürdiger Informationen präsentiert."
logical_fallacies_desc = "Argumente, bei denen sich die Schlussfolgerung nicht logischerweise aus den Prämissen ergibt. Auch bekannt als Non-Sequitur."
impossible_expecations_desc = "Unrealistische Standards der Sicherheit fordern, bevor man die Wissenschaft akzeptiert."
cherry_picking_desc = "Sorgfältige Auswahl von Daten, die eine Position zu bestätigen scheinen, während andere Daten ignoriert werden, die dieser Position widersprechen."
conspiracy_theory_desc = "Eine Verschwörung zur Umsetzung eines üblen Plans vermuten, wie das Verbergen der Wahrheit oder das Weitergeben von Falschinformationen."


class Strategy(str, Enum):
    f"""
    Pseudo-Experten: {fake_experts_desc}
    Logischer Trugschluss: {logical_fallacies_desc}
    Unerfüllbare Erwartungen: {impossible_expecations_desc}
    Rosinenpickerei: {cherry_picking_desc}
    Verschwörungsmythen: {conspiracy_theory_desc}
    """
    FAKE_EXPERTS = "Pseudo-Experten"
    LOGICAL_FALLACIES = "Logischer Trugschluss"
    IMPOSSIBLE_EXPECTATIONS = "Unerfüllbare Erwartungen"
    CHERRY_PICKING = "Rosinenpickerei"
    CONSPIRACY_THEORIES = "Verschwörungsmythen"

    def get_description(self) -> str:
        if self == Strategy.FAKE_EXPERTS:
            return fake_experts_desc
        elif self == Strategy.LOGICAL_FALLACIES:
            return logical_fallacies_desc
        elif self == Strategy.IMPOSSIBLE_EXPECTATIONS:
            return impossible_expecations_desc
        elif self == Strategy.CHERRY_PICKING:
            return cherry_picking_desc
        elif self == Strategy.CONSPIRACY_THEORIES:
            return conspiracy_theory_desc
        else:
            raise NotImplementedError(f"{self} not implemented.")


class AppliedStrategy(BaseModel):
    strategy: Strategy = Field(
        description="Die Strategie der Desinformation, welche möglicherweise angewendet wurde."
    )
    content: str = Field(
        description="Der Textstelle des Textes, bei der möglicherweise die Strategie der Desinformation angewendet wurde."
    )

    @classmethod
    def return_example_list(cls) -> list[AppliedStrategy]:
        return [
            AppliedStrategy(
                content="Das Klima hat sich in der Vergangenheit wegen natürlichen Ursachen verändert, also haben die heutigen Veränderungen ebenfalls natürliche Ursachen.",
                strategy=Strategy.LOGICAL_FALLACIES,
            ),
            AppliedStrategy(
                content="Wissenschaftler können nicht einmal das Wetter in der nächsten Woche vorhersagen. Wie sollen sie also das Wetter in 100 Jahren vorhersagen können?",
                strategy=Strategy.IMPOSSIBLE_EXPECTATIONS,
            ),
        ]

    def create_action(self, original_text: str, openai_client: AzureOpenAI) -> str:
        system_prompt = "Du bist ein Experte, das darauf spezialisiert ist, Menschen beim Hinterfragen von Argumenten zu unterstützen."

        text = original_text.replace("\n", " ")
        prompt = f"""
        Du erhältst einen originalen Text und eine Textpassage daraus.
        Für diese Testpassage wurde identifiziert, dass eventuell die Strategie {self.strategy.value} zur Verbreitung von Desinfomration verwendet wurde.
        Die Strategie {self.strategy.value} umfasst dabei folgendes: {self.strategy.get_description()}

        Deine Aufgaben:
            Erläutere in Bezug auf die Textpassage, wie die Strategie {self.strategy.value} möglicherweise angewendet wurde (maximal 2 prägnante Sätze).
            Gib zuzsätzlich konkrete Handlungsanweisungen, wie überprüft werden kann, ob die Strategie {self.strategy.value} tatsächlich angewendet wurde (maximal ein prägnanter Satz).
            Verwende dabei einfache Alltagssprache.
            Statt "In der Textpassage" kannst du einfach mit "Hier" Bezug zur Passage nehmen.
            Berücksichtige unbedingt, dass noch nicht bestätigt ist, dass die Strategie {self.strategy.value} wirklich angewendet wurde. Formuliere dementsprechend Teile passend im Konjunktiv.

        Input:
            Originaler Text: {text}
            Textpassage, bei der die potenzielle Strategie {self.strategy.value} identifiziert wurde: {self.content}
        
        Prägnante Erläuterung der potenziellen Strategie {self.strategy.value} in Bezug auf die Textpassage + konkrete Handlungsanweisungen, um dies zu überprüfen:
        """

        completion = openai_client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
        )

        return completion.choices[0].message.content

    @classmethod
    def stringify_long(cls, strategies: list[AppliedStrategy], original_text: str, openai_client: AzureOpenAI) -> str:
        strategy_map: dict[Strategy, list[AppliedStrategy]] = {}
        for strategy in strategies:
            if strategy.strategy not in strategy_map:
                strategy_map[strategy.strategy] = []
            strategy_map[strategy.strategy].append(strategy)
        texts = []
        for strategy, applied_strategies in strategy_map.items():
            texts.append(f"### {strategy.value}")
            for applied_strategy in applied_strategies:
                texts.append(f"> {applied_strategy.content}\n\n{applied_strategy.create_action(original_text=original_text, openai_client=openai_client)}")
            texts.append("\n\n")
        return "\n".join(texts)
    
    @classmethod
    def stringify_short(cls, strategies: list[AppliedStrategy]) -> str:
        #group for strategy
        strategy_map: dict[Strategy, list[AppliedStrategy]] = {}
        for strategy in strategies:
            if strategy.strategy not in strategy_map:
                strategy_map[strategy.strategy] = []
            strategy_map[strategy.strategy].append(strategy)
        return "\n".join([f"\t- {strategy.value} ({len(applied_strategies)}x)" for strategy, applied_strategies in strategy_map.items()])

    @classmethod
    def construct_answer_from_list(
        cls,
        strategies: list[AppliedStrategy],
        original_text: str,
        openai_client: AzureOpenAI,
    ) -> str:
        individual_strategies_long = AppliedStrategy.stringify_long(strategies, original_text, openai_client)
        individual_strategies_short = AppliedStrategy.stringify_short(strategies=strategies)

        if len(strategies) == 0:
            return f"# {get_ampel(strategies)}\n\nEs wurden keine Anzeichen auf Strategien für Desinformation gefunden."

        return f"""# {get_ampel(strategies)}

## Es liegen ggf. folgende Strategien von Desinformation vor
{individual_strategies_short}

## Individuelle Textstellen
{individual_strategies_long}"""


AppliedStrategy.model_rebuild()


class ExtractedStrategies(BaseModel):
    strategies: list[AppliedStrategy]


def identify_strategies(
    user_message: str, openai_client: AzureOpenAI
) -> list[AppliedStrategy]:
    """identifies strategies from a user message"""

    system_prompt = "Du bist ein sorgfältiger Desinformation-Experte, welcher aus Texten die verwendeten Strategien für Desinformation identifiziert."

    prompt = """
    Deine Aufgabe ist es, aus dem [TEXT] Strategien für Desinformationen zu identifizieren und zusammen mit den zugehörigen Textstellen zu extrahieren.
    Beachte, dass die gleiche Strategie an mehreren Stellen im [TEXT] vorkommen kann.
    Außerdem kann die gleiche Textstelle auch mehrere Strategien umfassen.
    
    Hier sind Beispiele für die verschiedenen Strategien des Desinformation:
    $PLACEHOLDER_STRATEGY_EXAMPLES

    [TEXT]
    $PLACEHOLDER_TEXT

    Verwendete Strategien des [TEXT]s mit zugehörigen Textstellen:
    """
    prompt = prompt.replace("$PLACEHOLDER_TEXT", user_message)
    prompt = prompt.replace("$PLACEHOLDER_STRATEGY_EXAMPLES", get_strategy_examples())

    client = instructor.from_openai(openai_client)

    completion: ExtractedStrategies = client.chat.completions.create(
        model=deployment,
        response_model=ExtractedStrategies,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=0
    )

    return [AppliedStrategy(**strategy.model_dump()) for strategy in completion.strategies]

    # return AppliedStrategy.return_example_list()


def is_first_message(messages: list[dict]) -> bool:
    return len(messages) == 1


def get_ampel(strategies: list[AppliedStrategy]) -> str:
    if len(strategies) == 0:
        return "Ampel grün"
    elif len(strategies) < 2:
        return "Ampel gelb"
    else:
        return "Ampel rot"


def get_strategy_examples() -> str:
    df = pd.read_excel("./Beispiele.xlsx", sheet_name="Sheet1")
    df.sort_values(by="PLURV-Kategorie")
    strategy_description = {
        "P": Strategy.FAKE_EXPERTS,
        "L": Strategy.LOGICAL_FALLACIES,
        "U": Strategy.IMPOSSIBLE_EXPECTATIONS,
        "R": Strategy.CHERRY_PICKING,
        "V": Strategy.CONSPIRACY_THEORIES
    }

    def get_category_examples():
        for strategy in strategy_description.keys():
            examples = "\n".join(
                [
                    f"\tBeispiel {i}: {example}"
                    for i, example in enumerate(
                        df[df["PLURV-Kategorie"] == strategy]["Aussage"]
                        .to_list()
                    )
                ]
            )
            yield f"Strategie: {strategy_description[strategy]}\n{examples}"

    return "---".join(get_category_examples())
