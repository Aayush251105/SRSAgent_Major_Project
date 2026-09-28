from config import LLMConfig
from agents.srs_agent import SRSAgent
from llm.ollama_provider import OllamaProvider
from llm.grok_provider import GrokProvider
from parsers.input_adapter import InputAdapter
from parsers.pdf_parser import PDFParser
from parsers.docx_parser import DOCXParser
from processors.requirement_detector import RequirementDetector


def create_provider(config: LLMConfig):
    """Create the configured LLM provider."""

    if config.provider == "ollama":
        return OllamaProvider(
            model=config.model,
            host=config.ollama_host
        )

    if config.provider == "grok":
        if not config.grok_api_key:
            raise ValueError("Set XAI_API_KEY in SRSAgent/.env to use the Grok provider")
        return GrokProvider(
            model=config.model,
            api_key=config.grok_api_key
        )

    raise ValueError(f"Unsupported LLM provider: {config.provider}")


def parse_input(input_data, input_type):
    """Parse document input into a common document representation."""

    if input_type == "pdf":
        return PDFParser().parse(input_data)

    if input_type == "docx":
        return DOCXParser().parse(input_data)

    if input_type == "text":
        return {
            "text": input_data
        }

    raise ValueError(f"Unsupported input type: {input_type}")


def main(input_data):
    config = LLMConfig()

    adapter = InputAdapter()
    adapted_input = adapter.adapt(input_data)

    input_type = adapted_input["type"]

    document = parse_input(
        adapted_input["data"],
        input_type
    )

    if input_type == "text" and not document["text"].strip():
        raise ValueError("Input text is empty")
    if input_type == "pdf" and not document["text"].strip():
        raise ValueError(
            "No selectable text was found in the PDF. Scanned PDFs need OCR, which is not included in V1."
        )

    detector = RequirementDetector()
    if input_type in {"pdf", "docx"}:
        candidates = detector.detect(
            document,
            input_type
        )
    else:
        candidates = detector.detect_text(document["text"])

    if not candidates:
        return []

    provider = create_provider(config)

    agent = SRSAgent(
        llm_provider=provider
    )

    requirements = agent.extract(candidates)

    return requirements


if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Extract requirements from SRS text or a PDF/DOCX file.")
    parser.add_argument("input", help="Plain text, or a path to a .pdf/.docx file")
    args = parser.parse_args()

    # A single CLI string that names an existing file is treated as a path;
    # otherwise it is processed as literal plain text.
    result = main(args.input)

    print(json.dumps([requirement.model_dump(mode="json") for requirement in result], indent=2))
