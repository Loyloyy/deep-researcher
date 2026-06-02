"""Thin Gradio UI over the headless core.

Topic in -> live progress (streamed logs) -> report + structured artifact.
The artifact JSON is editable; "Refine" launches a new version from it (parent_id).
All pipeline logic stays in core/run_research; this is presentation only.

Run:  python -m deep_researcher.ui.gradio_app
"""
from __future__ import annotations

import json
import logging
import queue
import threading

from ..core import run_research


class _QueueLogHandler(logging.Handler):
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record):
        try:
            self.q.put(self.format(record))
        except Exception:
            pass


def _run_streaming(topic: str, brief: str, parent_id: str | None):
    """Generator yielding (log_text, report_md, artifact_json) as the run progresses."""
    q: queue.Queue = queue.Queue()
    handler = _QueueLogHandler(q)
    handler.setFormatter(logging.Formatter("%(asctime)s %(name)s: %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    prev_level = root.level
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    result: dict = {}

    def worker():
        try:
            report, artifact = run_research(topic, brief, parent_id=parent_id or None)
            result["report"] = report
            result["artifact"] = artifact
        except Exception as e:  # surface errors into the log pane
            logging.getLogger("deep_researcher.ui").exception("run failed: %s", e)
            result["error"] = str(e)

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    logs: list[str] = []
    while t.is_alive() or not q.empty():
        try:
            logs.append(q.get(timeout=0.3))
            yield "\n".join(logs[-400:]), "", ""
        except queue.Empty:
            continue
    root.removeHandler(handler)
    root.setLevel(prev_level)

    if "error" in result:
        yield "\n".join(logs) + f"\n\nERROR: {result['error']}", "", ""
        return
    artifact = result["artifact"]
    yield (
        "\n".join(logs) + f"\n\n✅ done — artifact {artifact.id} v{artifact.version}",
        result["report"],
        artifact.model_dump_json(indent=2),
    )


def build_ui():
    import gradio as gr

    with gr.Blocks(title="deep-researcher") as demo:
        gr.Markdown("# deep-researcher\nGeneric deep research pipeline — topic in, cited report + structured artifact out.")
        with gr.Row():
            topic = gr.Textbox(label="Topic", scale=3, placeholder="e.g. speculative decoding for LLM inference")
            run_btn = gr.Button("Research", variant="primary", scale=1)
        brief = gr.Textbox(label="Brief / focus (optional)", lines=2)
        with gr.Row():
            logs = gr.Textbox(label="Progress", lines=14, max_lines=14, autoscroll=True)
        with gr.Tab("Report"):
            report = gr.Markdown()
        with gr.Tab("Artifact"):
            artifact_json = gr.Code(label="DeepResearchArtifact (editable)", language="json")
            with gr.Row():
                parent_id = gr.Textbox(label="Refine artifact_id", placeholder="dra-... (leave blank for new)")
                refine_btn = gr.Button("Refine from this artifact")

        run_btn.click(
            lambda tp, br: (yield from _run_streaming(tp, br, None)),
            inputs=[topic, brief],
            outputs=[logs, report, artifact_json],
        )

        def _refine(tp, br, pid, current_json):
            pid = pid.strip()
            if not pid and current_json:
                try:
                    pid = json.loads(current_json).get("id", "")
                except Exception:
                    pid = ""
            yield from _run_streaming(tp, br, pid or None)

        refine_btn.click(
            _refine,
            inputs=[topic, brief, parent_id, artifact_json],
            outputs=[logs, report, artifact_json],
        )

    return demo


def main() -> int:
    build_ui().launch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
