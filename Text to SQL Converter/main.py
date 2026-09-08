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
    final_prompt=f""" generate mysql sql query based on the below table schema:
    {schema}
    qustion- {user_input}
    Acceptance criteria- 
    Only provide sql. dont add any text or character before and after sql script.
    for joins first preference 'Left Join' and then 'Inner Join'.
    Always perform Select operation.
    Don't perform any Update, Insert and Delete operation if asked by user. Reply "This Operation can not be perform".

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




