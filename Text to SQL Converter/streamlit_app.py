import re
from urllib.parse import quote

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from db_connect import query_execution, table_schema


load_dotenv()

st.set_page_config(
    page_title="Text to SQL GPT",
    page_icon=":bar_chart:",
    layout="wide",
)

st.title("Text to SQL GPT")
st.write("Ask questions about your database using natural language.")

client = OpenAI()


if "history" not in st.session_state:
    st.session_state.history = []


@st.cache_data
def get_database_schema():
    return table_schema()


def clean_sql(sql_query):
    sql_query = sql_query.strip()
    sql_query = re.sub(
        r"^```sql\s*",
        "",
        sql_query,
        flags=re.IGNORECASE,
    )
    sql_query = re.sub(r"^```\s*", "", sql_query)
    sql_query = re.sub(r"\s*```$", "", sql_query)
    return sql_query.strip()


def is_read_only_query(sql_query):
    normalized_query = sql_query.strip().lower()
    return normalized_query.startswith(("select", "with"))


def display_previous_results():
    if not st.session_state.history:
        return

    st.divider()
    st.subheader("Previous Results")

    for result_number, item in enumerate(
        st.session_state.history,
        start=1,
    ):
        st.markdown(f"### Question {result_number}")
        st.write(item["question"])

        with st.expander("View Generated SQL", expanded=False):
            st.code(item["query"], language="sql")

        st.dataframe(
            item["result"],
            use_container_width=True,
        )

        csv_data = item["result"].to_csv(index=False).encode("utf-8")
        result_text = item["result"].to_string(index=False)

        email_subject = quote(
            "Text to SQL GPT - Query Result"
        )
        email_body = quote(
            f"Query Result:\n\n{result_text}"
        )
        mailto_link = (
            f"mailto:?subject={email_subject}"
            f"&body={email_body}"
        )

        download_column, spacer_column, email_column = st.columns(
            [1, 6, 1]
        )

        with download_column:
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name=f"query_result_{result_number}.csv",
                mime="text/csv",
                key=f"download_{result_number}",
            )

        with email_column:
            st.markdown(
                f"""
                <a href="{mailto_link}" target="_blank">
                    <button style="
                        padding: 0.45rem 1rem;
                        cursor: pointer;
                        border: 1px solid #888;
                        border-radius: 4px;
                        background-color: transparent;
                        white-space: nowrap;
                    ">
                        Email Result
                    </button>
                </a>
                """,
                unsafe_allow_html=True,
            )


try:
    schema = get_database_schema()
except Exception as error:
    st.error(f"Unable to load the database schema: {error}")
    st.stop()


# Display existing results first.
display_previous_results()

st.divider()
st.subheader("Ask Another Question")

with st.form(
    key="question_form",
    clear_on_submit=True,
):
    user_input = st.text_area(
        "Ask your question",
        placeholder=(
            "Example: Show the top 10 customers by total sales"
        ),
        height=120,
    )

    submit_question = st.form_submit_button(
        "Generate SQL and Run Query",
        type="primary",
    )


if submit_question:
    if not user_input.strip():
        st.warning("Please enter a question first.")
        st.stop()

    final_prompt = f"""
Generate a MySQL SQL query based on the table schema below.

Table schema:
{schema}

Question:
{user_input}

Acceptance criteria:
- Only provide SQL.
- Do not add explanations, markdown, or text before or after the SQL.
- For joins, prefer LEFT JOIN first and INNER JOIN second.
- Generate only a read-only SELECT or WITH query.
- Never perform INSERT, UPDATE, DELETE, DROP, ALTER,
  or other data-changing operations.
- Display records limit- If User asked for ALL Records or set any Specific Limit  else 100 records
"""

    try:
        with st.spinner("Generating SQL..."):
            response = client.responses.create(
                model="gpt-5.6-luna",
                input=final_prompt,
            )

        generated_query = clean_sql(response.output_text)

        if not is_read_only_query(generated_query):
            st.error(
                "Only read-only SELECT queries are allowed."
            )
            st.stop()

        with st.spinner("Running query..."):
            result = query_execution(generated_query)

        st.session_state.history.append(
            {
                "question": user_input,
                "query": generated_query,
                "result": result,
            }
        )

        st.rerun()

    except Exception as error:
        st.error(f"An error occurred: {error}")