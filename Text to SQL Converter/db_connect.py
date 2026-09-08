from sqlalchemy import create_engine
import pandas as pd
import pymysql as py
from dotenv import load_dotenv
import os

load_dotenv()
db_url=os.getenv("db_connection_details")#db_connection_details= DATABASE+DRIVER://USERNAME:PASSWORD@HOST:PORT/DATABASE


engine=create_engine(db_url)

def query_execution(query):
    with engine.connect() as con:
        df=pd.read_sql(query,con)
    return df

#fetching all available databases
def all_db_names():
    get_db_name=f"""
        select 
        distinct
        t.table_schema
        from information_schema.columns as t
        where table_schema not in ('mysql','information_schema','performance_schema','sys')
        ;
                """
    schema_query=query_execution(get_db_name)
    return schema_query
df=pd.DataFrame(all_db_names())
db_name= tuple([i for i in df.TABLE_SCHEMA])


def all_table_names():
    get_table_names=f"""
        select 
        distinct
        t.table_name
        from information_schema.columns as t
        where t.table_schema in {db_name} ;
                """
    table_query=query_execution(get_table_names)
    return table_query
df1=pd.DataFrame(all_table_names())

tbl=tuple([i for i in df1.TABLE_NAME])

def table_schema():
    table_names=all_table_names()
    get_schema=f"""
        select 
        t.table_schema,
        t.table_name,
        t.column_name,
        t.data_type
        from information_schema.columns as t
        where t.table_schema='ai_engineering' 
        and  t.table_name in {tbl};
                """
    final_query=query_execution(get_schema)
    return final_query


# result=table_schema()
# print(result)
# print(tuple(tbl))
