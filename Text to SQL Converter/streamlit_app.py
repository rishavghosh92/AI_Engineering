import html
import os
import re
import smtplib
from email.message import EmailMessage
from typing import List, Literal

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, Field

from db_connect import all_db_names, get_table_schema, query_execution


load_dotenv()

CONTEXT_EXCHANGES = 3

st.set_page_config(
    page_title="Text to SQL GPT",
    page_icon=":bar_chart:",
    layout="wide",
)

st.title("Text to SQL GPT")
st.write(
    "Ask questions about the available MySQL databases using natural language."
)
st.caption(
    "Only the latest 3 conversation exchanges are used as model context. "
    "The History panel stores all completed questions."
)


class TextToSQL(BaseModel):
    query: str = Field(
        description="Valid MySQL SQL only. No markdown or explanation."
    )
    tables_used: str = Field(
        description="Tables used and their relationships."
    )
    explanation: str = Field(
        description="Concise plain-language explanation of the result."
    )
    accuracy: int = Field(ge=0, le=100)
    allowed_operations: Literal["SELECT", "WITH"]
    rejected_operations: List[
        Literal[
            "INSERT",
            "UPDATE",
            "DELETE",
            "DROP",
            "ALTER",
            "TRUNCATE",
            "CREATE",
            "GRANT",
            "REVOKE",
            "RENAME",
            "CALL",
            "OTHER",
        ]
    ]
    record_limit: str = Field(
        description=(
            "All records when requested, the requested limit when "
            "specified, otherwise 100."
        )
    )
    join_preference: str = Field(
        description="Prefer LEFT JOIN before INNER JOIN."
    )


client = OpenAI()
model_name = os.getenv("OPENAI_MODEL", "gpt-5.6-luna")


def initialize_session_state():
    defaults = {
        # Complete UI history. This is never limited.
        "previous_questions": [],
        "generated_sql": [],
        "query_results": [],
        "explanations": [],
        "history": [],

        # Separate model conversation context.
        "conversation_history": [
            {
                "role": "system",
                "content": (
                    "You are a MySQL expert and text-to-SQL assistant."
                ),
            }
        ],
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


initialize_session_state()


@st.cache_data
def load_database_names():
    database_df = all_db_names().copy()
    database_df.columns = [
        column.lower() for column in database_df.columns
    ]

    if "table_schema" not in database_df.columns:
        raise ValueError(
            "The database list does not contain table_schema."
        )

    return sorted(
        database_df["table_schema"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )


@st.cache_data
def load_complete_schema():
    schema_df = get_table_schema().copy()
    schema_df.columns = [
        column.lower() for column in schema_df.columns
    ]

    required_columns = {
        "table_schema",
        "table_name",
        "column_name",
        "data_type",
    }

    missing_columns = required_columns.difference(schema_df.columns)

    if missing_columns:
        raise ValueError(
            f"Schema is missing columns: {', '.join(sorted(missing_columns))}"
        )

    return schema_df


def remove_markdown_fences(sql_query: str) -> str:
    cleaned_query = sql_query.strip()

    cleaned_query = re.sub(
        r"^```(?:mysql|sql)?\s*",
        "",
        cleaned_query,
        flags=re.IGNORECASE,
    )

    cleaned_query = re.sub(
        r"\s*```$",
        "",
        cleaned_query,
    )

    return cleaned_query.strip()


def validate_read_only_sql(sql_query: str) -> str:
    query = remove_markdown_fences(sql_query)

    if not query:
        raise ValueError("The generated SQL query is empty.")

    if not re.match(
        r"^(SELECT|WITH)\b",
        query,
        flags=re.IGNORECASE,
    ):
        raise ValueError(
            "Only SELECT and WITH queries are allowed."
        )

    blocked_patterns = [
        r"\bINSERT\b",
        r"\bUPDATE\b",
        r"\bDELETE\b",
        r"\bDROP\b",
        r"\bALTER\b",
        r"\bTRUNCATE\b",
        r"\bCREATE\b",
        r"\bGRANT\b",
        r"\bREVOKE\b",
        r"\bRENAME\b",
        r"\bCALL\b",
        r"\bLOAD\s+DATA\b",
        r"\bINTO\s+(OUTFILE|DUMPFILE)\b",
    ]

    for pattern in blocked_patterns:
        if re.search(
            pattern,
            query,
            flags=re.IGNORECASE,
        ):
            raise ValueError(
                "The generated SQL contains a prohibited operation."
            )

    query_without_semicolon = query.rstrip(";").strip()

    if ";" in query_without_semicolon:
        raise ValueError(
            "Multiple SQL statements are not allowed."
        )

    return query_without_semicolon


def get_recent_conversation():
    conversation_history = st.session_state.conversation_history

    system_message = conversation_history[0]
    recent_messages = conversation_history[1:][
        -(CONTEXT_EXCHANGES * 2):
    ]

    return [
        system_message,
        *recent_messages,
    ]


def format_recent_conversation() -> str:
    recent_conversation = get_recent_conversation()
    conversation_lines = []

    for message in recent_conversation:
        role = message["role"].upper()
        content = message["content"]

        conversation_lines.append(
            f"{role}:\n{content}"
        )

    return "\n\n".join(conversation_lines)


def save_conversation_exchange(
    question: str,
    structured_response: TextToSQL,
    result_df: pd.DataFrame,
):
    result_text = result_df.to_string(index=False)

    st.session_state.conversation_history.extend(
        [
            {
                "role": "user",
                "content": question,
            },
            {
                "role": "assistant",
                "content": (
                    f"Tables used:\n"
                    f"{structured_response.tables_used}\n\n"
                    f"Generated SQL:\n"
                    f"{structured_response.query}\n\n"
                    f"Explanation:\n"
                    f"{structured_response.explanation}\n\n"
                    f"Query result:\n"
                    f"{result_text}"
                ),
            },
        ]
    )

    system_message = st.session_state.conversation_history[0]

    recent_messages = st.session_state.conversation_history[1:][
        -(CONTEXT_EXCHANGES * 2):
    ]

    st.session_state.conversation_history = [
        system_message,
        *recent_messages,
    ]


def generate_sql(
    question: str,
    schema_df: pd.DataFrame,
) -> TextToSQL:
    schema_text = schema_df.to_string(index=False)
    recent_conversation = format_recent_conversation()

    prompt = f"""
You are a MySQL text-to-SQL assistant.

Use the recent conversation for context when helpful. The current question
may refer to previous questions, results, tables, or entities.

Only the latest {CONTEXT_EXCHANGES} conversation exchanges are included
in the conversation context.

The selected database in the Streamlit sidebar is only for display.
It must not filter, restrict, or control SQL generation.

Use the complete schema below. Tables from different databases may be joined.

Use fully qualified names for cross-database joins:

database_name.table_name

Recent conversation:
{recent_conversation}

Complete schema:
{schema_text}

Current user question:
{question}

Rules:
- Generate valid MySQL SQL.
- The query field must contain SQL only.
- Do not use markdown fences.
- Only SELECT and WITH queries are allowed.
- Always perform read-only operations.
- Never use MySQL reserved words as column aliases.
- Use descriptive, context-appropriate aliases for calculated columns
  and rankings.
- Prefer LEFT JOIN over INNER JOIN.
- If the user requests all records, return all records.
- If the user specifies a limit, follow it.
- Otherwise, limit the result to 100 rows.
- Reject INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, CREATE,
  GRANT, REVOKE, RENAME, CALL, and all other write operations.
- The explanation must describe the expected result in plain language.
- Do not include SQL inside the explanation.
"""

    response = client.responses.parse(
        model=model_name,
        input=prompt,
        text_format=TextToSQL,
    )

    parsed_response = response.output_parsed

    if parsed_response is None:
        raise ValueError(
            "The model did not return structured output."
        )

    parsed_response.query = validate_read_only_sql(
        parsed_response.query
    )

    return parsed_response


def dataframe_to_html(result_df: pd.DataFrame) -> str:
    return result_df.to_html(
        index=False,
        border=1,
        justify="left",
        escape=True,
    )


def send_result_email(
    question: str,
    result_df: pd.DataFrame,
    recipient: str,
):
    sender_email = os.getenv("EMAIL_ADDRESS")
    sender_password = os.getenv("EMAIL_APP_PASSWORD")
    smtp_server = os.getenv(
        "SMTP_SERVER",
        "smtp.gmail.com",
    )
    smtp_port = int(
        os.getenv("SMTP_PORT", "465")
    )

    if not sender_email or not sender_password:
        raise ValueError(
            "EMAIL_ADDRESS and EMAIL_APP_PASSWORD must be configured."
        )

    email_message = EmailMessage()
    email_message["Subject"] = "Text to SQL GPT Result"
    email_message["From"] = sender_email
    email_message["To"] = recipient

    plain_text_result = result_df.to_string(index=False)

    email_message.set_content(
        f"Question:\n\n"
        f"{question}\n\n"
        f"Query Result:\n\n"
        f"{plain_text_result}"
    )

    safe_question = html.escape(question)
    result_html = dataframe_to_html(result_df)

    email_message.add_alternative(
        f"""
        <html>
            <body>
                <h3>Question</h3>
                <p>{safe_question}</p>

                <h3>Query Result</h3>
                {result_html}
            </body>
        </html>
        """,
        subtype="html",
    )

    with smtplib.SMTP_SSL(
        smtp_server,
        smtp_port,
    ) as smtp:
        smtp.login(
            sender_email,
            sender_password,
        )
        smtp.send_message(email_message)


def display_result_history():
    for index, item in enumerate(
        st.session_state.history,
        start=1,
    ):
        st.subheader(f"Question {index}")
        st.write(item["question"])

        with st.expander(
            "View Generated SQL",
            expanded=False,
        ):
            st.code(
                item["generated_sql"],
                language="sql",
            )

        st.dataframe(
            item["result"],
            use_container_width=True,
            hide_index=True,
        )

        download_column, spacer_column, email_column = st.columns(
            [2, 5, 3]
        )

        with download_column:
            st.download_button(
                label="Download CSV",
                data=item["result"]
                .to_csv(index=False)
                .encode("utf-8"),
                file_name=f"query_result_{index}.csv",
                mime="text/csv",
                key=f"download_csv_{index}",
            )

        with email_column:
            recipient = st.text_input(
                "Recipient email",
                key=f"recipient_email_{index}",
            )

            if st.button(
                "Email Result",
                key=f"email_result_{index}",
                use_container_width=True,
            ):
                if not recipient.strip():
                    st.warning(
                        "Enter a recipient email address."
                    )
                else:
                    try:
                        send_result_email(
                            question=item["question"],
                            result_df=item["result"],
                            recipient=recipient.strip(),
                        )
                        st.success(
                            "Email sent successfully."
                        )
                    except Exception as error:
                        st.error(
                            f"Email sending failed: {error}"
                        )

        st.caption(item["explanation"])
        st.divider()


try:
    database_names = load_database_names()
    complete_schema = load_complete_schema()
except Exception as error:
    st.error(
        f"Schema loading failed: {error}"
    )
    st.stop()


with st.sidebar:
    st.header("Database")

    selected_database = st.selectbox(
        "Display database",
        options=database_names,
        key="selected_display_database",
    )

    st.caption(
        "This selection is for display only and does not affect "
        "SQL generation."
    )

    st.subheader("Schema Details")

    selected_schema = complete_schema[
        complete_schema["table_schema"] == selected_database
    ]

    for table_name in sorted(
        selected_schema["table_name"].unique()
    ):
        st.markdown(f"**{table_name}**")

        table_details = selected_schema[
            selected_schema["table_name"] == table_name
        ][
            ["column_name", "data_type"]
        ].rename(
            columns={
                "column_name": "Column",
                "data_type": "Type",
            }
        )

        st.dataframe(
            table_details,
            use_container_width=True,
            hide_index=True,
            key=f"schema_{selected_database}_{table_name}",
        )

    st.subheader("History")

    st.caption(
        "All completed questions are shown here. "
        "This list is independent of model context."
    )

    if not st.session_state.previous_questions:
        st.caption("No questions yet.")
    else:
        for index, question in enumerate(
            st.session_state.previous_questions,
            start=1,
        ):
            st.markdown(
                f"{index}. {question}"
            )


display_result_history()

st.subheader("Ask a Question")

with st.form(
    "question_form",
    clear_on_submit=True,
):
    user_question = st.text_area(
        "Natural-language question",
        placeholder=(
            "Example: Show the ten customers with the "
            "highest total purchases."
        ),
        height=120,
        key="question_input",
    )

    submitted = st.form_submit_button(
        "Generate SQL and Run Query",
        type="primary",
    )


if submitted:
    question = user_question.strip()

    if not question:
        st.warning(
            "Please enter a question."
        )
        st.stop()

    try:
        with st.spinner("Generating SQL..."):
            structured_response = generate_sql(
                question=question,
                schema_df=complete_schema,
            )
    except Exception as error:
        st.error(
            f"SQL generation failed: {error}"
        )
        st.stop()

    try:
        with st.spinner("Executing query..."):
            result_df = query_execution(
                structured_response.query
            )
    except Exception as error:
        st.error(
            f"Query execution failed: {error}"
        )
        st.stop()

    # These lists store every completed query for the UI.
    st.session_state.previous_questions.append(
        question
    )

    st.session_state.generated_sql.append(
        structured_response.query
    )

    st.session_state.query_results.append(
        result_df
    )

    st.session_state.explanations.append(
        structured_response.explanation
    )

    st.session_state.history.append(
        {
            "question": question,
            "generated_sql": structured_response.query,
            "result": result_df,
            "explanation": structured_response.explanation,
        }
    )

    # Only the latest three exchanges are retained for future prompts.
    save_conversation_exchange(
        question=question,
        structured_response=structured_response,
        result_df=result_df,
    )

    st.rerun()