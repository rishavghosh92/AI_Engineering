from openai import OpenAI
from dotenv import load_dotenv
from pydantic import BaseModel,Field
from typing import Literal,Optional
from db_connect import query_execution,get_table_schema


load_dotenv()

class text_to_sql(BaseModel):
    query : str = Field(description="only provide sql")
    tables_used : str = Field(description="mention table names used in SQL query with explantion and their relationship")
    explanation : str = Field(description="provide explanation on generated answer in between 20 to 50 words")
    accuracy : int = Field (description= "provide accuracy percentage of generated answer",ge=0,le=100)
    allowed_operations : Literal["SELECT","WITH"]= Field(description="only SELECT & WITH operations are allowed")
    rejected_operations : Literal["INSERT","UPDATE","DELETE","GRANT","CREATE","TRUNCATE","DROP"] = Field(description=" INSERT , UPDATED , DELETE , GRANT , CREATE , TRUNCATE , DROP are not allowed")
    record_limit : str = Field(description="provide all records if user asked else show 10 records by default")
    join_preference : str = Field(description=" prefer left join first and then inner join ")


client=OpenAI()
history=[]
history.append({"role":"system","content":"you are a data engineer."})

schema=get_table_schema()

while True:
    # history_details=history
    user_input=input("Ask your Question: ")
    if user_input.lower()=='exit':
        break
    history.append({"role":"user","content":user_input})
    
    final_prompt= f""" provide sql query based on user input and table schema:
    user input= {history}
    schema= {schema}
    """

    response=client.responses.parse(model="gpt-5.6-luna",
                                     input=final_prompt,
                                     text_format=text_to_sql
                                     )
    history.append({"role":"assistant","content":response.output_parsed.explanation})

    # print(history)
    #print(final_prompt)
    print(response.output_parsed.query)
    print(query_execution(response.output_parsed.query))
    print("Explanation: ",response.output_parsed.explanation)
    print("Additional Informations: ",response.output_parsed.tables_used)
    # print(response.output_parsed.accuracy)
    # print(response.output_parsed.operation)
    # print(response.output_parsed.limit)
