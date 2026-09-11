import html
import os
import re
import smtplib
from email.message import EmailMessage

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

from db_connect import (
    all_db_names,
    get_table_schema,
    query_execution,
)


load_dotenv()

st.set_page_config(
    page_title="Text to SQL GPT",
    page_icon=":bar_chart:",
    layout="wide",
)

st.title("Text to SQL GPT")
st.write(
    "Ask questions about all available databases using natural language."
)

client = OpenAI()

if "history" not in st.session_state:
    st.session_state.history = []


@st.cache_data
def load_database_names():
    database_df = all_db_names()
    database_df.columns = [
        column.lower() for column in database_df.columns
    ]

    return sorted(
        database_df["table_schema"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )


@st.cache_data
def load_complete_schema():
    schema_df = get_table_schema()
    schema_df.columns = [
        column.lower() for column in schema_df.columns
    ]

    return schema_df


def remove_code_fences(sql_query):
    cleaned_query = sql_query.strip()

    cleaned_query = re.sub(
        r"^```(?:sql)?\s*",
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


def validate_read_only_sql(sql_query):
    query = remove_code_fences(sql_query)

    if not query:
        raise ValueError("The generated SQL query is empty.")

    if not re.match(r"^(SELECT|WITH)\b", query, re.IGNORECASE):
        raise ValueError(
            "Only SELECT and WITH queries are allowed."
        )

    blocked_operations = (
        r"\bINSERT\b",
        r"\bUPDATE\b",
        r"\bDELETE\b",
        r"\bDROP\b",
        r"\bALTER\b",
        r"\bTRUNCATE\b",
        r"\bCREATE\b",
        r"\bRENAME\b",
        r"\bGRANT\b",
        r"\bREVOKE\b",
        r"\bCALL\b",
        r"\bLOAD\s+DATA\b",
        r"\bINTO\s+(OUTFILE|DUMPFILE)\b",
    )

    for operation in blocked_operations:
        if re.search(operation, query, re.IGNORECASE):
            raise ValueError(
                "The generated query contains a prohibited operation."
            )

    query_without_semicolon = query.rstrip(";").strip()

    if ";" in query_without_semicolon:
        raise ValueError(
            "Multiple SQL statements are not allowed."
        )

    return query_without_semicolon


def generate_sql(question, complete_schema):
    schema_text = complete_schema.to_string(index=False)

    prompt = f"""
You are a MySQL text-to-SQL assistant.

The user question is independent of the database selected in the
application sidebar.

The sidebar selection is used only to display database information.
Do not filter the schema based on the sidebar selection.

You may use tables from any database shown in the complete schema.
You may join tables from different databases.

For cross-database joins, fully qualify table names:
database_name.table_name

Complete schema for all available databases:
{schema_text}

User question:
{question}

SQL generation rules:
- Generate MySQL SQL.
- Return only SQL.
- Do not return explanations or markdown.
- Generate only SELECT or WITH queries.
- Always perform read-only operations.
- Prefer LEFT JOIN over INNER JOIN.
- Use tables from different databases when required.
- Fully qualify cross-database table names.
- If the user requests all records, return all records.
- If the user specifies a limit, follow that limit.
- Otherwise, return a maximum of 100 records.
- Never generate INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE,
  CREATE, RENAME, GRANT, REVOKE, CALL, or other write operations.

Return only the SQL query.
"""

    response = client.responses.create(
        model="gpt-5.6-luna",
        input=prompt,
    )

    return validate_read_only_sql(response.output_text)


def dataframe_to_html(result_df):
    table_html = result_df.to_html(
        index=False,
        border=0,
        classes="result-table",
        justify="left",
        escape=True,
    )

    return f"""
    <style>
        body {{
            font-family: Arial, sans-serif;
            color: #222222;
        }}

        .result-table {{
            border-collapse: collapse;
            width: 100%;
            font-size: 14px;
        }}

        .result-table th {{
            background-color: #1f4e78;
            color: white;
            border: 1px solid #b7c9d6;
            padding: 8px;
            text-align: left;
        }}

        .result-table td {{
            border: 1px solid #b7c9d6;
            padding: 8px;
            text-align: left;
        }}

        .result-table tr:nth-child(even) {{
            background-color: #f2f6f8;
        }}
    </style>

    {table_html}
    """


def send_result_email(question, result_df, recipient):
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
            "EMAIL_ADDRESS and EMAIL_APP_PASSWORD must be configured "
            "in the .env file."
        )

    safe_question = html.escape(question)
    result_table = dataframe_to_html(result_df)

    plain_text_result = result_df.to_string(index=False)

    email_message = EmailMessage()
    email_message["Subject"] = "Text to SQL GPT Result"
    email_message["From"] = sender_email
    email_message["To"] = recipient

    email_message.set_content(
        f"Question:\n\n"
        f"{question}\n\n"
        f"Query Result:\n\n"
        f"{plain_text_result}"
    )

    email_message.add_alternative(
        f"""
        <html>
            <body>
                <h3>Question</h3>
                <p>{safe_question}</p>

                <h3>Query Result</h3>
                {result_table}
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
    for result_number, item in enumerate(
        st.session_state.history,
        start=1,
    ):
        st.subheader(f"Question {result_number}")
        st.write(item["question"])

        with st.expander(
            "View Generated SQL",
            expanded=False,
        ):
            st.code(item["query"], language="sql")

        st.dataframe(
            item["result"],
            use_container_width=True,
        )

        csv_data = item["result"].to_csv(
            index=False
        ).encode("utf-8")

        download_column, spacer_column, email_column = st.columns(
            [2, 5, 3]
        )

        with download_column:
            st.download_button(
                label="Download CSV",
                data=csv_data,
                file_name=f"query_result_{result_number}.csv",
                mime="text/csv",
                key=f"download_csv_{result_number}",
            )

        with email_column:
            recipient = st.text_input(
                "Recipient email",
                key=f"recipient_email_{result_number}",
            )

            send_email = st.button(
                "Email Result",
                key=f"send_email_{result_number}",
                use_container_width=True,
            )

            if send_email:
                if not recipient.strip():
                    st.warning(
                        "Enter a recipient email address."
                    )
                else:
                    try:
                        with st.spinner("Sending email..."):
                            send_result_email(
                                question=item["question"],
                                result_df=item["result"],
                                recipient=recipient.strip(),
                            )

                        st.success("Email sent successfully.")

                    except Exception as error:
                        st.error(
                            f"Email sending failed: {error}"
                        )

        st.divider()


try:
    database_names = load_database_names()
    complete_schema = load_complete_schema()

except Exception as error:
    st.error(f"Unable to load database schema: {error}")
    st.stop()


with st.sidebar:
    st.header("Database")

    selected_database = st.selectbox(
        "Display database",
        options=database_names,
        key="display_database",
    )

    st.caption(
        "This selection only controls the schema displayed below. "
        "It does not control question processing."
    )

    display_schema = complete_schema[
        complete_schema["table_schema"] == selected_database
    ]

    st.subheader("Tables and Schema")

    if display_schema.empty:
        st.warning(
            "No tables found for the selected database."
        )
    else:
        table_names = sorted(
            display_schema["table_name"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        for table_name in table_names:
            st.markdown(f"**{table_name}**")

            table_schema = display_schema[
                display_schema["table_name"] == table_name
            ][["column_name", "data_type"]]

            table_schema = table_schema.rename(
                columns={
                    "column_name": "Column",
                    "data_type": "Type",
                }
            )

            st.dataframe(
                table_schema,
                hide_index=True,
                use_container_width=True,
                key=f"schema_{selected_database}_{table_name}",
            )


display_result_history()

st.subheader("Ask your Question")

with st.form(
    key="question_form",
    clear_on_submit=True,
):
    user_question = st.text_area(
        "Ask your question",
        placeholder=(
            "Example: Compare customers from one database "
            "with purchases from another database"
        ),
        height=120,
        key="question_input",
    )

    submitted = st.form_submit_button(
        "Generate SQL and Run Query",
        type="primary",
    )


if submitted:
    if not user_question.strip():
        st.warning("Please enter a question.")
        st.stop()

    try:
        with st.spinner("Generating SQL..."):
            generated_query = generate_sql(
                question=user_question,
                complete_schema=complete_schema,
            )

    except Exception as error:
        st.error(f"SQL generation failed: {error}")
        st.stop()

    try:
        with st.spinner("Executing query..."):
            query_result = query_execution(generated_query)

    except Exception as error:
        st.error(f"Query execution failed: {error}")
        st.stop()

    st.session_state.history.append(
        {
            "question": user_question,
            "query": generated_query,
            "result": query_result,
        }
    )

    st.rerun()