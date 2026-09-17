# Text to SQL Converter

A Streamlit application that converts natural-language questions into read-only MySQL queries using an OpenAI model. The generated query is validated, executed against the configured database connection, and displayed as a table in the application.

## What This Application Does

The application helps users explore MySQL databases without writing SQL manually.

A typical workflow is:

1. Connect to a MySQL database using a SQLAlchemy connection URL.
2. Discover available databases and their table schemas from MySQL `information_schema`.
3. Accept a question written in natural language.
4. Send the question and the complete discovered schema to the OpenAI model.
5. Parse the model response into a structured Pydantic object.
6. Validate that the generated SQL is read-only.
7. Execute the validated query.
8. Display the results in Streamlit.
9. Store the completed question and result in the current session history.

## Main Features

- Natural-language to MySQL SQL generation
- Automatic database and schema discovery
- Support for tables across multiple databases
- Fully qualified table names for cross-database queries
- Structured model output using Pydantic
- Read-only SQL validation
- `SELECT` and `WITH` query support
- Automatic default limit of 100 rows when no limit is requested
- Follow-up questions using recent conversation context
- Complete query history for the current Streamlit session
- CSV downloads for query results
- Optional email delivery of query results
- Database and table details shown in the sidebar

## Project Files

```text
Text to SQL Converter/
├── db_connect.py       # Database connection and schema-discovery functions
├── main.py              # Supporting or experimental Python file
├── prompts.txt         # Prompt-related notes
├── req.txt             # Python dependencies
├── streamlit_app.py    # Main Streamlit application
├── README.md           # Documentation for this application
├── pyvenv.cfg          # Virtual-environment configuration
└── myenv/              # Local virtual environment; do not commit to Git
```

## Technologies Used

- Python
- Streamlit
- OpenAI API
- Pydantic
- Pandas
- SQLAlchemy
- PyMySQL
- `python-dotenv`
- MySQL

## Requirements

Before running the application, install or have access to:

- Python 3.9 or later
- A reachable MySQL server
- A MySQL user with permission to read metadata and query the required tables
- An OpenAI API key
- Network access to the OpenAI API

A read-only MySQL user is strongly recommended.

## Installation

From the project directory, create and activate a virtual environment:

```bash
cd "Text to SQL Converter"
python3 -m venv myenv
source myenv/bin/activate
```

On Windows PowerShell, activation is usually:

```powershell
myenv\Scripts\Activate.ps1
```

Install the dependencies:

```bash
pip install -r req.txt
```

## Environment Configuration

Create a file named `.env` inside the `Text to SQL Converter` directory.

Minimum configuration:

```env
OPENAI_API_KEY=your_openai_api_key
OPENAI_MODEL=your_openai_model

db_connection_details=mysql+pymysql://username:password@host:3306/database_name
```

The connection URL follows this format:

```text
mysql+pymysql://USERNAME:PASSWORD@HOST:PORT/DATABASE
```

Example:

```env
db_connection_details=mysql+pymysql://report_user:password@localhost:3306/sales
```

Do not commit `.env` to Git. It can contain database passwords and API keys.

### Optional Email Configuration

Emailing results is optional. To enable it, add the following variables:

```env
EMAIL_ADDRESS=your_email@example.com
EMAIL_APP_PASSWORD=your_email_app_password
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
```

For Gmail, use an app password rather than your normal account password. The email feature uses SMTP over SSL.

## Running the Application

From the `Text to SQL Converter` directory, run:

```bash
streamlit run streamlit_app.py
```

Streamlit normally opens the application at:

```text
http://localhost:8501
```

If the browser does not open automatically, copy the URL into a browser.

## How to Use the Application

### 1. Review the Sidebar

The sidebar contains:

- A list of discovered database names
- A display selector for one database
- The tables and columns available in the selected database
- The current session's question history

The selected database is currently for display only. It does not restrict schema discovery or control which database the model uses when generating SQL.

### 2. Ask a Question

Enter a natural-language question in the text area. For example:

```text
Show the ten customers with the highest total purchases.
```

Then select **Generate SQL and Run Query**.

The application will generate SQL and execute it only if the generated query passes validation.

### 3. Review the Result

Completed questions appear in the main page history. Each result includes:

- The original question
- The generated SQL in an expandable section
- The returned data in a table
- A plain-language explanation
- A CSV download button
- An optional email form

### 4. Ask Follow-up Questions

The application retains the complete history for display, but only the latest three question-and-answer exchanges are included as context for future model requests.

For example:

```text
Show the top ten customers by total purchases.
```

A follow-up question could be:

```text
Now show their email addresses.
```

The model can use the recent conversation to interpret references such as “their” or “those customers.”

## How Schema Discovery Works

`db_connect.py` reads metadata from MySQL's `information_schema.columns` table.

It discovers:

- Database names
- Table names
- Column names
- Data types

The application excludes these system or internal schemas:

- `mysql`
- `information_schema`
- `performance_schema`
- `sys`

The complete schema is provided to the model so it can identify relevant tables and columns. Tables from different databases may be joined using fully qualified names such as:

```sql
database_name.table_name
```

## SQL Safety Validation

Before a generated query is executed, the application checks that:

- The query is not empty.
- The query begins with `SELECT` or `WITH`.
- The query does not contain prohibited write or administrative operations.
- The query contains only one SQL statement.
- Markdown code fences are removed if the model includes them accidentally.

The following operations are rejected:

- `INSERT`
- `UPDATE`
- `DELETE`
- `DROP`
- `ALTER`
- `TRUNCATE`
- `CREATE`
- `GRANT`
- `REVOKE`
- `RENAME`
- `CALL`
- `LOAD DATA`
- `INTO OUTFILE`
- `INTO DUMPFILE`

This validation is an application-level safeguard. It is not a replacement for database permissions. Configure the database account used by this application with read-only permissions whenever possible.

## Query Generation Rules

The prompt sent to the model instructs it to:

- Generate valid MySQL SQL.
- Use only read-only operations.
- Avoid Markdown and explanations in the SQL field.
- Avoid reserved words as aliases.
- Use descriptive aliases for calculated values and rankings.
- Prefer `LEFT JOIN` over `INNER JOIN`.
- Return all records when the user explicitly requests all records.
- Follow a user-provided row limit.
- Use a default limit of 100 rows when no limit is specified.
- Explain the expected result in plain language without including SQL in the explanation.

## Session State and History

Streamlit session state stores:

- Previous questions
- Generated SQL statements
- Query result DataFrames
- Explanations
- Complete display history
- Recent conversation context for the model

This history exists only in the active Streamlit session unless the application is extended with persistent storage. Restarting the application or creating a new session may clear it.

## Emailing Results

For each completed query, enter a recipient email address and select **Email Result**.

The email contains:

- The original question
- A plain-text version of the result
- An HTML table containing the result

The question is HTML-escaped before being inserted into the HTML email. Email sending requires valid SMTP settings and credentials in `.env`.

## Downloading Results

Select **Download CSV** below a result to download the current DataFrame as a UTF-8 CSV file.

The downloaded file is generated in memory and is not automatically stored on the server.

## Troubleshooting

### Schema loading failed

Check that:

- The MySQL server is running.
- `db_connection_details` exists in `.env`.
- The connection URL is valid.
- The database user can read `information_schema.columns`.
- The configured host, port, username, and password are correct.

### SQL generation failed

Check that:

- `OPENAI_API_KEY` is configured.
- The selected model name is available to the API account.
- The machine has network access to the OpenAI API.
- The complete schema is not too large for the selected model's context window.

### Query execution failed

The generated SQL may reference a missing table or column, use an incorrect join, or violate the database user's permissions. Review the generated SQL shown in the error or history and compare it with the schema displayed in the sidebar.

### Email sending failed

Check that:

- `EMAIL_ADDRESS` and `EMAIL_APP_PASSWORD` are configured.
- The SMTP server and port are correct.
- The email provider allows SMTP access.
- The recipient address is valid.

## Security Recommendations

- Never commit `.env`, API keys, database passwords, or email app passwords.
- Use a dedicated read-only database user.
- Restrict that user to only the required databases and tables.
- Avoid exposing the Streamlit server publicly without authentication.
- Review generated SQL before using the application with sensitive data.
- Be careful when emailing query results because they may contain confidential information.
- Add the local virtual environment directory to `.gitignore`.

## Known Limitations

- The selected database in the sidebar does not currently restrict SQL generation.
- Conversation history is stored only for the active Streamlit session.
- The model receives the complete discovered schema on each request, which may become expensive or exceed context limits for very large database installations.
- SQL validation is based on query text patterns and should be reinforced with database permissions.
- Email configuration is global and is not managed through the Streamlit interface.
- The application assumes the configured database connection can access the schemas needed for discovery and query execution.

## Future Improvements

Possible future improvements include:

- Restricting SQL generation to the database selected in the sidebar
- Adding authentication for the Streamlit application
- Persisting query history in a database
- Adding query cancellation and execution timeouts
- Improving SQL parsing with a dedicated SQL parser
- Adding automated tests for SQL validation and schema discovery
- Adding pagination for large query results
- Allowing users to select which schemas are sent to the model
- Adding query cost or performance warnings
- Supporting additional database engines

## License and Project Status

This project is part of the `AI_Engineering` repository and is intended for learning and experimentation. Review the repository's license and contribution guidelines if they are added later.
