from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

from agent.graph import graph


def export_graph():
    project_root = Path(__file__).resolve().parent.parent

    docs_dir = project_root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    output_path = docs_dir / "langgraph_workflow.mmd"

    mermaid = graph.get_graph().draw_mermaid()

    output_path.write_text(mermaid, encoding="utf-8")

    print("=" * 70)
    print("LangGraph Mermaid 다이어그램 export 완료")
    print(f"저장 위치: {output_path}")
    print("=" * 70)
    print(mermaid)


if __name__ == "__main__":
    export_graph()