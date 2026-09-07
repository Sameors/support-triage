import streamlit as st
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from pathlib import Path
from src.agent_loop import run_agent_on_case, infrastructure
from data.evals.checks import check_pass_1, check_pass_2



dataset_path = Path(__file__).parent.parent.parent / "data" / "evals" / "eval_dataset.json"

if "combined_results" not in st.session_state:
    st.session_state.combined_results = None

st.write("### Support Triage Eval")

if st.button("Run eval suite"):
    with open(dataset_path, "r") as f:
        dataset = json.load(f)

    combined_results = []
               
    with st.spinner("Running eval suite..."):
        for case in dataset:
            result = run_agent_on_case(case, infrastructure)
            p1 = check_pass_1(case, result)
            p2 = check_pass_2(case, result)
            combined_results.append({"case_id": case["id"], "pass_1": p1, "pass_2": p2,"trace": result["trace"]})

    st.session_state.combined_results = combined_results

if st.session_state.combined_results:
    table_rows = []
    for r in st.session_state.combined_results:
        table_rows.append({"case_id":r["case_id"],
                           "pass_1":r["pass_1"]["status"],
                           "seq":r["pass_2"]["sequence_status"],
                           "layer":r["pass_2"]["layer_status"] if r["pass_2"]["layer_check_applicable"] else "n/a"
                           })
    
    event = st.dataframe(
        table_rows,
        on_select="rerun",
        selection_mode="single-row",
        key="eval_table"
        
        
    )
    if event.selection["rows"]:
        selected_idx = event.selection["rows"][0]  # first (only, since single-row mode) selected index
        selected_case = st.session_state.combined_results[selected_idx]
        st.write(f"### {selected_case['case_id']}")
        for step in selected_case["trace"]["steps"]:
            
                for step in selected_case["trace"]["steps"]:
                    with st.container(border=True):
                        st.write(f"**{step['name']}** ({step['step_type']})")
                        if step["name"] == "classify_case":
                            st.write(f"category: {step['details']['category']} · urgency: {step['details']['urgency']}")
                        elif step["name"] == "search_knowledge_base":
                            st.write(f"top_similarity: {step['details']['top_similarity']:.2f}")
                        elif step["name"] == "propose_resolution":
                            st.write(f"- layer_1: {step['details']['layer_1']['resolve'] if step['details']['layer_1'] else 'None'}")
                            st.write(f"- layer_2: {step['details']['layer_2']['resolve'] if step['details']['layer_2'] else 'None'}")
                            st.write(f"- layer_3: {step['details']['layer_3']['resolve'] if step['details']['layer_3'] else 'None'}")
                        elif step["name"] == "route_to_queue":
                            st.write(f"queue: {step['details']['queue']}")
                        elif step["name"] == "escalate":
                            st.write(f"reason: {step['details']['reason']}")
                break        
    