from __future__ import annotations

import instructor
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
        endpoint =os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")

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
            strategies: list[AppliedStrategy] = identify_strategies(user_message, openai_client=self.llm)
            result = AppliedStrategy.construct_answer_from_list(strategies=strategies, original_text=user_message, openai_client=self.llm)
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

class Strategy(Enum, BaseModel):
    FAKE_EXPERTS = Field(default="Pseudo-Experten", description=fake_experts_desc)
    LOGICAL_FALLACIES = Field(default="Logischer Trugschluss", description=logical_fallacies_desc) 
    IMPOSSIBLE_EXPECTATIONS = Field(default="Unerfüllbare Erwartungen", description=impossible_expecations_desc) 
    CHERRY_PICKING = Field(default="Rosinenpickerei", description=cherry_picking_desc) 
    CONSPIRACY_THEORIES = Field(default="Verschwörungsmythen", description=conspiracy_theory_desc) 

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
    strategy: Strategy = Field(description="Die Strategie, welche möglicherweise angewendet wurde.")
    content: str = Field(description="Der Textstelle des Textes, auf die möglicherweise die Strategie angewendet wurde.")

    @classmethod
    def return_example_list(cls) -> list[AppliedStrategy]:
        return [
            AppliedStrategy(
                content="Das Klima hat sich in der Vergangenheit wegen natürlichen Ursachen verändert, also haben die heutigen Veränderungen ebenfalls natürliche Ursachen.",
                strategy=Strategy.LOGICAL_FALLACIES
            ),
            AppliedStrategy(
                content="Wissenschaftler können nicht einmal das Wetter in der nächsten Woche vorhersagen. Wie sollen sie also das Wetter in 100 Jahren vorhersagen können?",
                strategy=Strategy.IMPOSSIBLE_EXPECTATIONS
            )
        ]
    
    def create_action(self, original_text: str, openai_client: AzureOpenAI) -> str:
        system_prompt="Du bist ein Experte, das darauf spezialisiert ist, Menschen beim Hinterfragen von Argumenten zu unterstützen."
        
        text = original_text.replace("\n", " ")
        prompt = f"""
        Aufgabe:
            Du erhältst einen originalen Text und eine Textpassage daraus.
            Dazu wird eine Argumentationsstrategie angegeben, die eventuell angewendet wurde, sowie eine kurze Erklärung, was diese Strategie ist.

        Deine Aufgaben:
            Erläutere mit Hilfe der Textpassage wie die Strategie möglicherweise angewendet wurde und welche Aspekte recherchiert oder überlegt werden müssen, um zu entscheiden, ob die Strategie tatsächlich angewendet wurde.

        In deiner Antwort solltest du die Anwendung der Strategie anhand der Textpassage erläutern und eine konrete Handlungsanweisung geben, mit der überprüft werden kann, ob diese Strategie angewendet wurde.
        Fasse dich dabei sehr kurz (maximal 2 prägnante Sätze).
        Berücksichtige dabei, dass noch nicht bestätigt ist, dass die Strategie wirklich angewendet wurde. Formuliere dementsprechend Teile passend im Konjunktiv.

        Input:
            Originaler Text: {text}
            Textpassage: {self.content}
            Verwendete Strategie der Desinformation: {self.strategy.value}
            Erklärung der Strategie: {self.strategy.get_description()}
        """

        completion = openai_client.chat.completions.create(
            model=deployment, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]
        )

        return completion.choices[0].message.content
    
    
    def stringify_long(self, original_text: str, openai_client: AzureOpenAI) -> str:
        return f"""\t- Definition: {self.strategy.get_description()}
        \t- Passage: {self.content}
        \t- Individueller Denkauftrag: {self.create_action(original_text=original_text, openai_client=openai_client)}"""
    
    def stringify_short(self) -> str:
        return f"\t- {self.strategy.value}"

    @classmethod
    def construct_answer_from_list(cls, strategies: list[AppliedStrategy], original_text: str, openai_client: AzureOpenAI) -> str:
        individual_strategies_long = "\n\n".join([strategy.stringify_long(original_text, openai_client) for strategy in strategies])
        individual_strategies_short = "\n".join([strategy.stringify_short() for strategy in strategies])

        return f"""# {get_ampel(strategies)}


## Es liegen folgende Merkmale von Desinformation vor
{individual_strategies_short}

## Individuelle Anweisungen
{individual_strategies_long}"""
    
AppliedStrategy.model_rebuild()

class ExtractedStrategies(BaseModel):
    strategies: list[AppliedStrategy]

def identify_strategies(user_message: str, openai_client: AzureOpenAI) -> list[AppliedStrategy]:
    """ identifies strategies from a user message """

    system_prompt="Du bist ein sorgfältiger Desinformation-Experte, welcher aus Texten die verwendeten Strategien für Desinformation identifiziert."

    prompt = """
    Deine Aufgabe ist es, aus dem [TEXT] Strategien für Desinformationen zu identifizieren und zusammen mit den zugehörigen Textstellen zu extrahieren.

    Hier sind Beispiele für die verschiedenen Strategien:
    $PLACEHOLDER_STRATEGY_EXAMPLES

    [TEXT]
    $PLACEHOLDER_TEXT

    Verwendete Strategien des [TEXT]s:
    """
    prompt = prompt.replace("$PLACEHOLDER_TEXT", user_message)
    prompt = prompt.replace("$PLACEHOLDER_STRATEGY_EXAMPLES", get_strategy_examples())

    client = instructor.from_openai(openai_client)

    completion: ExtractedStrategies = client.chat.completions.create(
        model=deployment, response_model=ExtractedStrategies, messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}]
    )
    
    return [AppliedStrategy(**strategy) for strategy in completion.strategies]


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
    return ""