import enum
import pandas as pd
import yaml
import os

from sqlalchemy import create_engine, text
from sqlalchemy import Table, Column, Integer, Float, String, DateTime, Enum, MetaData, ForeignKey
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy_utils import database_exists, create_database

metadata = MetaData()

class TIPO_BARRA(enum.Enum):
    BT = 1
    MT = 2
    AT = 3

# TODO buscar o nome das tabelas diretamento do db
tabelas = ['linha','circuito', 'barra', 'analise', 'capacitor', 'equipamento']

analise_table = Table('analise', metadata,
                      Column('analise', Integer, primary_key=True),
                      Column('cenario_id', Integer, nullable=False),
                      Column('cenario', String(30)),
                      Column('empresa', String(30)),
                      Column('sub', String(30)),
                      Column('circuito', String(30), nullable=False),
                      Column('controle_id', Integer, nullable=False),
                      Column('controle', String(30)),
                      Column('data', DateTime),
                      Column('patamar_ini', Integer),
                      Column('patamar_fim', Integer),
                      )
circuito_table = Table('circuito', metadata,
                       Column('cenario_id', Integer),
                       Column('circuito', String(90)),
                       Column('controle_id', String(30)),
                       Column('patamar', Integer),
                       Column('hora', Integer),
                       Column('seg', Integer),
                       Column('p1', Float),
                       Column('p2', Float),
                       Column('p3', Float),
                       Column('q1', Float),
                       Column('q2', Float),
                       Column('q3', Float),
                       Column('p_losses', Float),
                       Column('q_losses', Float),
                       Column('p_losses_line', Float),
                       Column('q_losses_line', Float),
                       )
barra_table = Table('barra', metadata,
                    Column('cenario_id', Integer),
                    Column('circuito', String(90)),
                    Column('controle_id', String(30)),
                    Column('patamar', Integer),
                    Column('hora', Integer),
                    Column('seg', Integer),
                    Column('bus', String(90)),
                    Column('node', Integer),
                    Column('vln_pu', Float),
                    Column('v_base', Float),
                    Column('tipo', Enum(TIPO_BARRA)),
                    Column('kw',  Float),
                    Column('kvar',  Float),
                    Column('fp',  Float),
                    Column('distancia', Float)
                    )
linha_table = Table('linha', metadata,
                    Column('cenario_id', Integer),
                    Column('circuito', String(90)),
                    Column('controle_id', String(30)),
                    Column('linha', String(90)),
                    Column('patamar', Integer),
                    Column('hora', Integer),
                    Column('seg', Integer),
                    Column('v1', Float),
                    Column('distancia1', Float),
                    Column('v2', Float),
                    Column('distancia2', Float),
                    Column('node', Integer),
                    Column('tipo', Enum(TIPO_BARRA)),
                    )
equipamento_table = Table('equipamento', metadata,
                    Column('cenario_id', Integer),
                    Column('circuito', String(90)),
                    Column('nome', String(90)),
                    Column('controle_id', Integer),
                    Column('controle', String(30)),
                    Column('kvar', Float),
                    Column('pt_ratio', Float),
                    Column('ct_ratio', Float),
                    Column('ctrl_on', Float),
                    Column('ctrl_off', Float),
                    Column('delay', Integer),
                    Column('delay_off', Integer),
                    Column('dead_time', Integer),
                    Column('kv_base', Float)
                    )
capacitor_table = Table ('capacitor' , metadata,
                         Column('cenario_id', Integer),
                         Column('circuito', String(90)),
                         Column('controle_id', String(30)),
                         Column('nome', String(90)),
                         Column('patamar', Integer),
                         Column('hora', Integer),
                         Column('seg', Integer),
                         Column('step', Integer),
                         Column('vmag_1', Float),
                         Column('vmag_2', Float),
                         Column('vmag_3', Float),
                         Column('available_steps', Integer)
                         )

def nome_tabelas():
    return tabelas

def load_config(db = 'resultsDB', config_path="config_database.yml", var = None):

    application_path = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(application_path, config_path), 'r') as file:
        config = yaml.load(file, Loader=yaml.BaseLoader)

    if config_path == "config_database.yml":
        config = config.get("databases", {}).get(db)
    else:
        config = config.get(var, {}).get(db)

    if not config:
        raise ValueError(f"Configurações para '{db}' não foram encontradas.")
    return config

def create_connection(config_bdgd):
    """Função para criar uma conexão com o banco de dados SQL Server"""

    engine = create_engine(f"mssql+pyodbc://"
                           f"{config_bdgd['username']}:"
                           f"{config_bdgd['password']}@"
                           f"{config_bdgd['server']}/"
                           f"{config_bdgd['database']}?"
                           f"driver=ODBC+Driver+17+for+SQL+Server",
                           fast_executemany=True, pool_pre_ping=True)

    return engine

def check_cenario_exist(tabelas, feeder, cenario_id, controle_id):
    conf = load_config()
    engine = create_connection(conf)

    for tabela in tabelas:
        query = (f"Select count(*) as cenario_id from {tabela} where circuito = '{feeder}' and cenario_id = {cenario_id} "
                 f"and controle_id={controle_id} ")
        with engine.connect() as conn:
            res = pd.read_sql_query(sql=query, con=conn)
            count_reg = res.iloc[0]['cenario_id']
            if count_reg > 0 :
                try:
                    # conn.execute(text(f"TRUNCATE TABLE {tabela}"))
                    conn.execute(text(f"DELETE from {tabela} where circuito = '{feeder}' and cenario_id = {cenario_id} "
                                      f"and controle_id={controle_id}"))
                    conn.commit()
                except SQLAlchemyError as e:
                    #conn.execute(text(f"ALTER  TABLE {tabela} NOCHECK CONSTRAINT all"))
                    print(f'Erro: {e}')

def insert_data(tabela, data_dict):
    conf = load_config()
    engine = create_connection(conf)

    list_column= list(data_dict[0].keys())
    list_column = ""
    list_values = ""

    for key, value in data_dict[0].items():
        list_column += key + ', '
        list_values += ':'+ key + ', '

    list_column = list_column[:-2]
    list_values = list_values[:-2]
    with engine.connect() as conn:
        try:
            conn.execute(text(f"INSERT INTO {tabela} ({list_column}) "
                              f"VALUES ({list_values})"),
                         data_dict,
                         )
            conn.commit()
        except SQLAlchemyError as e:
            print(e)
    conn.close()

if __name__ == '__main__':

    conf = load_config('resultsDB')
    engine = create_connection(conf)
    if not database_exists(engine.url):
        create_database(engine.url)

    try:
        metadata.create_all(engine) # create the table
    except SQLAlchemyError as e:
        print(e)