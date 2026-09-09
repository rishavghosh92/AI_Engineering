import pandas as pd
from openai import OpenAI
from dotenv import load_dotenv
from db_connect import query_execution,table_schema
load_dotenv()
# client will fetch API key from .env file where OPENAI_API_KEY is created
client=OpenAI()


schema=table_schema()

while True:
    user_input=input("Ask your Qustion: ")
    if user_input.lower()=='exit':
        break
    final_prompt=f""" Generate MYSQL SQL query based on the below table schema:

    Table Schema-{schema}

    Qustion- {user_input}

    Acceptance criteria- 
    - Only provide SQL. 
    - do NOT add any explanations, text or markdown before and after SQL script.
    - for joins first preference 'Left Join' and 'Inner Join' second.
    - Generate only read-only SELECT and WITH query.
    - Never perform any UPDATE, INSERT and DELETE operation or other Data-Changing operations.
    - Display records limit- If User asked for ALL Records or set any Specific Limit  else 100 records

    """
    # # print(final_prompt)
    response=client.responses.create(model='gpt-5.6-luna',
                                        input=final_prompt)

    #print generated query
    query=response.output_text
    #print final output from generated query
    response=query_execution(response.output_text)

    print(query)
    print(response)




