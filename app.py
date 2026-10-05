import json
import sys
import threading
import time

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


def main(input_data, progress_callback=None):
    config = LLMConfig()

    adapter = InputAdapter()
    adapted_input = adapter.adapt(input_data)

    input_type = adapted_input["type"]
    if progress_callback:
        progress_callback("stage", {"message": f"Input detected as {input_type}"})

    if progress_callback:
        progress_callback("stage", {"message": "Parsing input"})
    document = parse_input(
        adapted_input["data"],
        input_type
    )
    if progress_callback:
        extracted_text = document.get("text")
        if extracted_text is None and input_type == "docx":
            extracted_text = "\n".join(item["text"] for item in document["paragraphs"])
        summary = f"Extracted {len(extracted_text or ''):,} text characters"
        if input_type == "pdf":
            summary += f" from {document['page_count']} pages"
        elif input_type == "docx":
            summary += f" from {document['paragraph_count']} paragraphs/table cells"
        progress_callback("stage", {"message": summary})
        progress_callback("parsed_preview", {
            "text": (extracted_text or "")[:2000],
            "truncated": len(extracted_text or "") > 2000,
        })

    if input_type == "text" and not document["text"].strip():
        raise ValueError("Input text is empty")
    if input_type == "pdf" and not document["text"].strip():
        raise ValueError(
            "No selectable text was found in the PDF. Scanned PDFs need OCR, which is not included in V1."
        )

    detector = RequirementDetector()
    if progress_callback:
        progress_callback("stage", {"message": "Detecting requirement candidates"})
    if input_type in {"pdf", "docx"}:
        candidates = detector.detect(
            document,
            input_type
        )
    else:
        candidates = detector.detect_text(document["text"])

    if not candidates:
        if progress_callback:
            progress_callback("stage", {"message": "No requirement candidates found"})
        return []

    if progress_callback:
        progress_callback("candidates", {"candidates": candidates})

    provider = create_provider(config)
    if progress_callback:
        progress_callback("stage", {
            "message": f"Starting {len(candidates)} extraction call(s) with {config.provider}/{config.model}"
        })

    agent = SRSAgent(
        llm_provider=provider
    )

    requirements = agent.extract(candidates, progress_callback=progress_callback)

    return requirements


class TerminalProgress:
    """Render progress and completed records on stderr, leaving stdout as JSON."""

    def __init__(self):
        self.started_at = time.monotonic()
        self.completed_durations = []
        self.total = 0
        self.current_index = None
        self.current_started_at = None
        self._stop_ticker = threading.Event()
        self._ticker = None
        self._lock = threading.Lock()

    @staticmethod
    def _format_duration(seconds):
        seconds = max(0, int(seconds))
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def _render_model_progress(self):
        with self._lock:
            completed = len(self.completed_durations)
            elapsed = time.monotonic() - self.started_at
            bar_width = 24
            filled = int(bar_width * completed / self.total) if self.total else 0
            bar = "#" * filled + "-" * (bar_width - filled)
            current_elapsed = time.monotonic() - self.current_started_at
            eta = "ETA calculating"
            if self.completed_durations:
                average = sum(self.completed_durations) / len(self.completed_durations)
                remaining_models = self.total - completed - 1
                eta_seconds = max(0, average * remaining_models + average - current_elapsed)
                eta = f"ETA ~{self._format_duration(eta_seconds)}"
            line = (
                f"\r[{bar}] {completed}/{self.total} complete | "
                f"REQ-{self.current_index:03d} generating | "
                f"current {self._format_duration(current_elapsed)} | "
                f"elapsed {self._format_duration(elapsed)} | {eta}"
            )
            print(line, end="", file=sys.stderr, flush=True)

    def _start_ticker(self):
        self._stop_ticker.clear()

        def tick():
            while not self._stop_ticker.wait(0.5):
                self._render_model_progress()

        self._ticker = threading.Thread(target=tick, daemon=True)
        self._ticker.start()
        self._render_model_progress()

    def _stop_current_ticker(self):
        if self._ticker is not None:
            self._stop_ticker.set()
            self._ticker.join()
            self._ticker = None
            print(file=sys.stderr)

    def __call__(self, event, payload):
        if event == "stage":
            print(f"[step] {payload['message']}", file=sys.stderr, flush=True)
        elif event == "parsed_preview":
            print("[step] Parsed text preview:", file=sys.stderr)
            print(payload["text"], file=sys.stderr)
            if payload["truncated"]:
                print("  ... (preview limited to 2,000 characters)", file=sys.stderr)
        elif event == "candidates":
            self.total = len(payload["candidates"])
            print(f"[step] Found {self.total} requirement candidate(s):", file=sys.stderr)
            for index, candidate in enumerate(payload["candidates"], start=1):
                source = candidate.get("source") or {}
                location = f" | source={source}" if source else ""
                print(f"  {index:03d}. {candidate['text']}{location}", file=sys.stderr)
        elif event == "requirement_start":
            self.current_index = payload["index"]
            self.current_started_at = time.monotonic()
            self._start_ticker()
        elif event == "requirement_done":
            self._stop_current_ticker()
            elapsed = time.monotonic() - self.current_started_at
            self.completed_durations.append(elapsed)
            requirement = payload["requirement"]
            print(
                f"[step] Completed {requirement.requirement_id} in "
                f"{self._format_duration(elapsed)}. Current result:",
                file=sys.stderr,
            )
            print(
                json.dumps(requirement.model_dump(mode="json"), indent=2),
                file=sys.stderr,
                flush=True,
            )
        elif event == "requirement_error":
            self._stop_current_ticker()
            print(
                f"[error] REQ-{payload['index']:03d} failed: {payload['error']}",
                file=sys.stderr,
                flush=True,
            )

    def finish(self, count):
        print(
            f"[done] Generated {count} requirement(s) in "
            f"{self._format_duration(time.monotonic() - self.started_at)}.",
            file=sys.stderr,
            flush=True,
        )


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Extract requirements from SRS text or a PDF/DOCX file.")
    parser.add_argument("input", help="Plain text, or a path to a .pdf/.docx file")
    args = parser.parse_args()

    # A single CLI string that names an existing file is treated as a path;
    # otherwise it is processed as literal plain text.
    progress = TerminalProgress()
    result = main(args.input, progress_callback=progress)
    progress.finish(len(result))

    output_text = json.dumps(
        [requirement.model_dump(mode="json") for requirement in result],
        indent=2,
        ensure_ascii=False,
    )

    output_dir = Path(__file__).resolve().parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    input_type = InputAdapter().detect(args.input)
    output_stem = Path(args.input).stem if input_type in {"pdf", "docx"} else "text_input"
    output_path = output_dir / f"{output_stem}_requirements.txt"
    output_path.write_text(output_text + "\n", encoding="utf-8")

    print(f"[saved] Full JSON-formatted text output: {output_path}", file=sys.stderr)
    print(output_text)
